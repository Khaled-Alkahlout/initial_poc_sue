"""De stappen van het proces als losse functies, zodat de Streamlit-UI en de tests dezelfde code gebruiken.

Er is geen eigen logica voor het beoordelen: de stappen roepen ``static_check``, ``run_query``, ``compare`` en
``measure`` aan, precies zoals ``evaluate()`` in ``scripts/run_validation.py`` dat doet. De UI laat alleen zien
wat daar tussendoor gebeurt.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cases.cases import CASES, make_ctx  # noqa: E402
from llm.client import SQL_BLOCK, SYSTEM, build_prompt, call_llm, extract_sql  # noqa: E402
from llm.context import CONDITIONS, build_context  # noqa: E402
from llm.prices import cost_usd  # noqa: E402
from scripts.run_validation import OK_STATES, TIMEOUT_MS  # noqa: E402
from validator.checker import compare, run_query, static_check  # noqa: E402
from validator.timing import SPEEDUP_THRESHOLD, measure  # noqa: E402

RESULTS = ROOT / "results"

# Modellen van de modelvergelijking, met hun OpenRouter-naam (de standaard) en de directe Anthropic-naam.
MODELS = {
    "Haiku 5.5": ("anthropic/claude-haiku-5.5", "claude-haiku-5-5"),
    "Sonnet 5.5": ("anthropic/claude-sonnet-5.5", "claude-sonnet-5-5"),
    "Opus 5.5": ("anthropic/claude-opus-5.5", "claude-opus-5-5"),
    "Fable 5.1 (naam niet bevestigd)": ("anthropic/claude-fable-5.1", "claude-fable-5-1"),
}

CONDITION_LABELS = {
    "C1_query": "C1 · alleen de query",
    "C2_schema": "C2 · query + schema",
    "C3_plan": "C3 · query + schema + uitvoeringsplan",
    "C4_stats": "C4 · query + schema + plan + statistieken",
}

VERDICTS = {
    "REJECTED_STATIC": ("error", "Afgekeurd bij de statische controle: geen toegestane SELECT. Er is niets uitgevoerd."),
    "REJECTED_NOT_EQUIVALENT": ("error", "Afgekeurd: het resultaat verschilt van het origineel op minstens één parameterset."),
    "EQUIVALENT_NOT_FASTER": ("warning", "Gelijkwaardig, maar niet aantoonbaar sneller (onder de drempel)."),
    "ACCEPTED": ("success", "Geaccepteerd: gelijk resultaat op alle geteste parametersets én aantoonbaar sneller."),
}


def case_by_name(name: str):
    """
    Find a case by its name.

    Parameters
    ----------
    name : str
        Name of the case, e.g. "top_customers".

    Returns
    -------
    Case
        The case with that name.
    """
    return next(c for c in CASES if c.name == name)


def connect(uri: str):
    """
    Open a connection in autocommit mode and check that it works.

    Parameters
    ----------
    uri : str
        Database URI.

    Returns
    -------
    psycopg.Connection
        Open connection.
    """
    conn = psycopg.connect(uri, autocommit=True, connect_timeout=5)
    conn.execute("SELECT 1")
    return conn


def param_table(case, ctx) -> list[dict]:
    """
    List the parameter sets of a case in a form that can be shown in a table.

    Parameters
    ----------
    case : Case
        The case.
    ctx : dict
        Context as returned by ``make_ctx``.

    Returns
    -------
    list of dict
        One row per parameter set: its label and every parameter value as text.
    """
    return [{"set": label, **{k: str(v) for k, v in p.items()}} for label, p in case.params(ctx)]


def build_prompt_for(conn, case, ctx, condition: str) -> tuple[dict, str]:
    """
    Build the context blocks and the user prompt for a condition.

    Parameters
    ----------
    conn : psycopg.Connection
        Open connection (schema, plan and statistics are read from the database).
    case : Case
        The case.
    ctx : dict
        Context as returned by ``make_ctx``.
    condition : str
        One of ``CONDITIONS``.

    Returns
    -------
    tuple of (dict, str)
        The blocks (key to text) and the prompt that is sent to the model.
    """
    blocks = build_context(conn, case, ctx, condition)
    return blocks, build_prompt(blocks)


def ask_model(prompt: str, model: str, provider: str, effort: str | None, max_tokens: int, original_sql: str) -> dict:
    """
    Send the prompt to the model and extract the SQL from the answer.

    Parameters
    ----------
    prompt : str
        User prompt.
    model : str
        Model name for the provider, or "mock" (returns the original query).
    provider : str
        "openrouter" or "anthropic".
    effort : str or None
        Thinking effort, or None for the default of the model.
    max_tokens : int
        Limit on output tokens, including thinking tokens.
    original_sql : str
        Original query; only used by the mock model.

    Returns
    -------
    dict
        The response of ``call_llm`` plus "sql" (the extracted query), "truncated" (cut off before a
        complete SQL block) and "cost_usd" (reported by the provider, otherwise computed from the price table).
    """
    resp = call_llm(prompt, model, max_tokens=max_tokens, original_sql=original_sql, provider=provider, effort=effort)
    resp["sql"] = extract_sql(resp["text"])
    resp["truncated"] = resp.get("stop_reason") == "max_tokens" and not SQL_BLOCK.search(resp["text"])
    reported = resp.get("cost_reported")
    resp["cost_usd"] = float(reported) if reported not in (None, "") else cost_usd(model, resp["input_tokens"], resp["output_tokens"])
    return resp


def check_equivalence(conn, case, sql: str, ctx) -> list[dict]:
    """
    Run the original and the candidate on every parameter set and compare the results.

    Parameters
    ----------
    conn : psycopg.Connection
        Open connection.
    case : Case
        Case with the original query, the parameter sets and the ORDER BY columns.
    sql : str
        The candidate query.
    ctx : dict
        Context as returned by ``make_ctx``.

    Returns
    -------
    list of dict
        One row per parameter set with "set", "status" (EQUIVALENT, TIE_AMBIGUOUS, a mismatch type or
        EXEC_ERROR), "detail", the row counts and the duration of both executions in milliseconds.
    """
    rows = []
    for label, p in case.params(ctx):
        try:
            o = run_query(conn, case.original, p, timeout_ms=TIMEOUT_MS)
            c = run_query(conn, sql, p, timeout_ms=TIMEOUT_MS)
        except psycopg.Error as e:
            rows.append({"set": label, "status": "EXEC_ERROR", "detail": f"{type(e).__name__}: {str(e)[:200]}",
                         "orig_rows": None, "cand_rows": None, "orig_ms": None, "cand_ms": None})
            continue
        cmp = compare(o, c, case.order_cols)
        rows.append({"set": label, "status": cmp.status, "detail": cmp.detail, "orig_rows": len(o.rows),
                     "cand_rows": len(c.rows), "orig_ms": round(o.ms, 1), "cand_ms": round(c.ms, 1)})
    return rows


def equivalent(eq_rows: list[dict]) -> bool:
    """
    Check whether the candidate was equivalent on every parameter set.

    Parameters
    ----------
    eq_rows : list of dict
        Output of ``check_equivalence``.

    Returns
    -------
    bool
        True when every status is EQUIVALENT or TIE_AMBIGUOUS.
    """
    return all(r["status"] in OK_STATES for r in eq_rows)


def check_timing(conn, case, sql: str, ctx, reps: int) -> dict:
    """
    Measure original and candidate alternately (ABAB) on the timing parameters of the case.

    Parameters
    ----------
    conn : psycopg.Connection
        Open connection.
    case : Case
        The case.
    sql : str
        The candidate query.
    ctx : dict
        Context as returned by ``make_ctx``.
    reps : int
        Number of timed repetitions per query.

    Returns
    -------
    dict
        The result of ``measure``: medians, IQRs, speedup, "faster" and the repetitions used.
    """
    return measure(conn, case.original, sql, case.timing_params(ctx), reps=reps)


def decide(static_ok: bool, eq_rows: list[dict] | None, timing: dict | None) -> str:
    """
    Combine the steps into one verdict, with the same rules as ``evaluate()``.

    Parameters
    ----------
    static_ok : bool
        Result of the static check.
    eq_rows : list of dict or None
        Output of ``check_equivalence``; None when the step was skipped.
    timing : dict or None
        Output of ``check_timing``; None when the step was skipped.

    Returns
    -------
    str
        REJECTED_STATIC, REJECTED_NOT_EQUIVALENT, EQUIVALENT_NOT_FASTER or ACCEPTED.
    """
    if not static_ok:
        return "REJECTED_STATIC"
    if not equivalent(eq_rows or []):
        return "REJECTED_NOT_EQUIVALENT"
    return "ACCEPTED" if timing and timing["faster"] else "EQUIVALENT_NOT_FASTER"


def run_all(conn, case, ctx, sql: str, reps: int) -> dict:
    """
    Validate one candidate in all steps, without any display. Used by the tests.

    Parameters
    ----------
    conn : psycopg.Connection
        Open connection.
    case : Case
        The case.
    ctx : dict
        Context as returned by ``make_ctx``.
    sql : str
        The candidate query.
    reps : int
        Number of timed repetitions.

    Returns
    -------
    dict
        Keys "static" (tuple of bool and message), "equivalence", "timing" and "verdict".
    """
    ok, msg = static_check(sql)
    eq = check_equivalence(conn, case, sql, ctx) if ok else None
    timing = check_timing(conn, case, sql, ctx, reps) if ok and equivalent(eq) else None
    return {"static": (ok, msg), "equivalence": eq, "timing": timing, "verdict": decide(ok, eq, timing)}


def stored_answers() -> list[dict]:
    """
    List the answers of earlier LLM runs that are saved in ``results/``.

    Returns
    -------
    list of dict
        One entry per saved answer: "run", "case", "condition", "rep", "model", "path" and the verdict
        that was given at the time ("old_verdict"). Newest runs first.
    """
    out = []
    for f in sorted(RESULTS.glob("**/llm-results.json"), reverse=True):
        run_dir = f.parent
        try:
            rows = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for r in rows:
            path = run_dir / "responses" / f"{r['case']}__{r['condition']}__r{r['rep']}.json"
            if path.exists():
                out.append({"run": str(run_dir.relative_to(RESULTS)), "case": r["case"], "condition": r["condition"],
                            "rep": r["rep"], "model": r.get("model", ""), "path": path,
                            "old_verdict": r.get("verdict", "")})
    return out


def load_answer(path: Path) -> dict:
    """
    Load one saved model answer.

    Parameters
    ----------
    path : Path
        A ``responses/<case>__<condition>__r<rep>.json`` file.

    Returns
    -------
    dict
        The response, in the same form as ``ask_model`` returns (missing fields get a default).
    """
    d = json.loads(path.read_text(encoding="utf-8"))
    d.setdefault("stop_reason", "")
    d.setdefault("truncated", False)
    d.setdefault("cost_usd", cost_usd(d.get("model", ""), d.get("input_tokens", 0), d.get("output_tokens", 0)))
    return d


__all__ = ["CASES", "CONDITIONS", "SYSTEM", "SPEEDUP_THRESHOLD", "make_ctx", "static_check"]
