"""Prompt opbouwen, de LLM aanroepen en de SQL uit het antwoord halen."""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

SYSTEM = """Je bent een PostgreSQL 16-expert. Je herschrijft een bestaande SELECT-query zodat die sneller draait.
Regels:
- Lever precies EEN SELECT-statement (CTE's mogen). Geen DDL, geen indexen, geen schemawijzigingen, geen SET.
- Het resultaat moet voor ELKE geldige parameterwaarde identiek zijn aan het origineel: dezelfde kolommen
  (namen en volgorde), dezelfde rijen en dezelfde volgorde volgens de ORDER BY van het origineel.
- Gebruik exact dezelfde parameters in de vorm %(naam)s. Schrijf een letterlijk procentteken als %%.
- Als je geen zinvolle verbetering ziet, geef dan de originele query ongewijzigd terug.
Antwoord met de query in een ```sql codeblok, gevolgd door hooguit drie zinnen uitleg."""

HEADERS = {
    "query": "Originele query",
    "schema": "Schema van de gebruikte tabellen (kolommen, constraints, indexen)",
    "plan": "Uitvoeringsplan van het origineel (EXPLAIN ANALYZE, BUFFERS) op representatieve parameters",
    "stats": "Statistieken (geschatte rijen per tabel, pg_stats voor de gebruikte kolommen)",
}

PROVIDERS = ("anthropic", "openrouter")
# Het basisadres kan in een test worden overschreven met de omgevingsvariabele OPENROUTER_BASE_URL.
OPENROUTER_DEFAULT_URL = "https://openrouter.ai/api/v1"
RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}
MAX_ATTEMPTS = 4


def build_prompt(blocks: dict) -> str:
    """
    Assemble the user prompt from the context blocks that belong to a condition.

    Parameters
    ----------
    blocks : dict
        Context blocks as returned by ``build_context``; possible keys are "query", "schema", "plan" and "stats".

    Returns
    -------
    str
        Prompt with one markdown section per block, followed by the rewrite instruction.
    """
    parts = []
    for key in ("query", "schema", "plan", "stats"):
        if key in blocks:
            fence = "sql" if key == "query" else ""
            parts.append(f"## {HEADERS[key]}\n```{fence}\n{blocks[key]}\n```")
    parts.append("Herschrijf de query zodat die sneller is en exact hetzelfde resultaat geeft.")
    return "\n\n".join(parts)


SQL_BLOCK = re.compile(r"```(?:sql|postgresql)?\s*\n(.*?)```", re.S | re.I)


def extract_sql(text: str) -> str:
    """
    Extract the SQL statement from an LLM response.

    Parameters
    ----------
    text : str
        Full response text. The first fenced code block is used; without a code block the whole text is used.

    Returns
    -------
    str
        The SQL without surrounding whitespace and without a trailing semicolon.
    """
    m = SQL_BLOCK.search(text)
    sql = (m.group(1) if m else text).strip()
    return sql[:-1].rstrip() if sql.endswith(";") else sql


def _call_anthropic(prompt: str, model: str, max_tokens: int, effort: str | None) -> dict:
    """
    Call the Anthropic Messages API directly.

    Parameters
    ----------
    prompt : str
        User prompt.
    model : str
        Anthropic model id, e.g. "claude-sonnet-5-5".
    max_tokens : int
        Hard limit on output tokens; thinking tokens count towards it.
    effort : str or None
        Effort level ("low", "medium", "high", ...); None leaves the model default.

    Returns
    -------
    dict
        Keys "text", "input_tokens", "output_tokens", "stop_reason", "cost_reported" (None) and "usage_raw".
    """
    import anthropic  # pas hier, zodat --dry-run en mock zonder dit pakket werken

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Zet eerst de omgevingsvariabele ANTHROPIC_API_KEY (zie README.md).")
    client = anthropic.Anthropic()
    kwargs = {}
    if effort:
        # extra_body werkt ook met een oudere versie van het anthropic-pakket
        kwargs["extra_body"] = {"output_config": {"effort": effort}}
    msg = client.messages.create(model=model, max_tokens=max_tokens, system=SYSTEM,
                                 messages=[{"role": "user", "content": prompt}], **kwargs)
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return {"text": text, "input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens,
            "stop_reason": msg.stop_reason or "unknown", "cost_reported": None,
            "usage_raw": {"input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens}}


def _post_json(url: str, body: dict, key: str, timeout: int = 600) -> dict:
    """
    POST a JSON body with a bearer token and return the parsed JSON answer, retrying transient errors.

    Parameters
    ----------
    url : str
        Full URL.
    body : dict
        JSON body.
    key : str
        API key, sent as a bearer token. It is never printed or put in an error message.
    timeout : int, default 600
        Seconds to wait for one answer.

    Returns
    -------
    dict
        The parsed JSON answer.

    Raises
    ------
    RuntimeError
        After a non-transient error or after the last attempt; the message holds the HTTP status and the server text.
    """
    data = json.dumps(body).encode("utf-8")
    last = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        req = urllib.request.Request(url, data=data, method="POST", headers={
            "Authorization": f"Bearer {key}", "Content-Type": "application/json", "User-Agent": "deepdive-kit/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            last = f"HTTP {e.code}: {detail}"
            if e.code not in RETRY_STATUS:
                raise RuntimeError(last) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = f"{type(e).__name__}: {e}"
        if attempt < MAX_ATTEMPTS:
            time.sleep(2 ** attempt)
    raise RuntimeError(f"na {MAX_ATTEMPTS} pogingen geen antwoord ({last})")


def _call_openrouter(prompt: str, model: str, max_tokens: int, effort: str | None) -> dict:
    """
    Call a model through the OpenRouter chat-completions API.

    Parameters
    ----------
    prompt : str
        User prompt.
    model : str
        OpenRouter slug, e.g. "anthropic/claude-sonnet-5.5".
    max_tokens : int
        Hard limit on output tokens; thinking tokens count towards it.
    effort : str or None
        Value for ``reasoning.effort``; None leaves the model default.

    Returns
    -------
    dict
        Keys "text", "input_tokens", "output_tokens", "stop_reason", "cost_reported" and "usage_raw".
    """
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("Zet eerst de omgevingsvariabele OPENROUTER_API_KEY (zie README.md).")
    base = os.environ.get("OPENROUTER_BASE_URL", OPENROUTER_DEFAULT_URL).rstrip("/")
    body = {"model": model, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            "usage": {"include": True}}
    if effort:
        body["reasoning"] = {"effort": effort, "exclude": True}
    data = _post_json(f"{base}/chat/completions", body, key)
    if "choices" not in data or not data["choices"]:
        raise RuntimeError(f"onverwacht antwoord: {json.dumps(data)[:300]}")
    choice = data["choices"][0]
    content = (choice.get("message") or {}).get("content")
    if isinstance(content, list):
        content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
    finish = choice.get("native_finish_reason") or choice.get("finish_reason") or "unknown"
    stop = {"length": "max_tokens", "stop": "end_turn", "end_turn": "end_turn", "max_tokens": "max_tokens"}.get(finish, finish)
    if choice.get("finish_reason") == "length":
        stop = "max_tokens"
    usage = data.get("usage") or {}
    return {"text": content or "", "input_tokens": int(usage.get("prompt_tokens") or 0),
            "output_tokens": int(usage.get("completion_tokens") or 0), "stop_reason": stop,
            "cost_reported": usage.get("cost"), "usage_raw": usage}


def call_llm(prompt: str, model: str, max_tokens: int = 4000, original_sql: str = "",
             provider: str = "anthropic", effort: str | None = None) -> dict:
    """
    Send a prompt to the LLM and return the response with token usage.

    Parameters
    ----------
    prompt : str
        User prompt as built by ``build_prompt``.
    model : str
        Model name for the chosen provider, or "mock" to return the original query unchanged without calling an API.
    max_tokens : int, default 4000
        Maximum number of output tokens. Thinking tokens count towards this limit.
    original_sql : str, default ""
        Original query; only used by the mock model.
    provider : str, default "anthropic"
        "anthropic" (direct, key in ANTHROPIC_API_KEY) or "openrouter" (key in OPENROUTER_API_KEY).
    effort : str or None, default None
        Effort level; None leaves the default of the model, which differs per model.

    Returns
    -------
    dict
        Keys "text" (response text), "input_tokens", "output_tokens", "seconds" (duration of the call),
        "stop_reason" ("end_turn" or "max_tokens" or another value of the provider), "cost_reported"
        (cost according to the provider, or None) and "usage_raw".
    """
    t0 = time.perf_counter()
    if model == "mock":
        text = f"```sql\n{original_sql}\n```\nMock: origineel ongewijzigd."
        return {"text": text, "input_tokens": 0, "output_tokens": 0, "seconds": 0.0,
                "stop_reason": "end_turn", "cost_reported": None, "usage_raw": {}}
    if provider == "anthropic":
        resp = _call_anthropic(prompt, model, max_tokens, effort)
    elif provider == "openrouter":
        resp = _call_openrouter(prompt, model, max_tokens, effort)
    else:
        raise SystemExit(f"Onbekende provider '{provider}'; kies uit {PROVIDERS}.")
    resp["seconds"] = round(time.perf_counter() - t0, 1)
    return resp
