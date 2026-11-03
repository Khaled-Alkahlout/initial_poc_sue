"""Prompt opbouwen, de LLM aanroepen en de SQL uit het antwoord halen."""
from __future__ import annotations

import os
import re
import time

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


def call_llm(prompt: str, model: str, max_tokens: int = 4000, original_sql: str = "") -> dict:
    """
    Send a prompt to the LLM and return the response with token usage.

    Parameters
    ----------
    prompt : str
        User prompt as built by ``build_prompt``.
    model : str
        Anthropic model name, or "mock" to return the original query unchanged without calling an API.
    max_tokens : int, default 4000
        Maximum number of output tokens.
    original_sql : str, default ""
        Original query; only used by the mock model.

    Returns
    -------
    dict
        Keys "text" (response text), "input_tokens", "output_tokens" and "seconds" (duration of the call).
    """
    t0 = time.perf_counter()
    if model == "mock":
        text = f"```sql\n{original_sql}\n```\nMock: origineel ongewijzigd."
        return {"text": text, "input_tokens": 0, "output_tokens": 0, "seconds": 0.0}
    if "/" in model or os.getenv("SUE_LLM_PROVIDER") == "openrouter":
        from llm.analysis import chat
        return chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}], model, max_tokens=max_tokens)
    import anthropic  # pas hier, zodat --dry-run en mock zonder dit pakket werken

    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("Zet eerst de omgevingsvariabele ANTHROPIC_API_KEY (zie README_LLM.md).")
    client = anthropic.Anthropic()
    msg = client.messages.create(model=model, max_tokens=max_tokens, system=SYSTEM,
                                 messages=[{"role": "user", "content": prompt}])
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return {"text": text, "input_tokens": msg.usage.input_tokens, "output_tokens": msg.usage.output_tokens,
            "seconds": round(time.perf_counter() - t0, 1)}
