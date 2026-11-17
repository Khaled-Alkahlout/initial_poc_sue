"""Draai het validatieframework op alle kandidaten en vergelijk de uitkomst met de verwachting.
Gebruik: python scripts/run_validation.py <db-uri> [--reps 7]"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cases.cases import CASES, make_ctx  # noqa: E402
from validator.checker import compare, run_query, static_check  # noqa: E402
from validator.timing import measure  # noqa: E402

OK_STATES = {"EQUIVALENT", "TIE_AMBIGUOUS"}


CACHE: dict = {}
TIMEOUT_MS = 120000


def evaluate(conn, case, cand, ctx, reps):
    """
    Validate one candidate against the original: static check, equivalence on all parameter sets, then timing.

    Parameters
    ----------
    conn : psycopg.Connection
        Open connection to the database.
    case : Case
        Case that holds the original query and its parameter sets.
    cand : Candidate
        Candidate rewrite to validate.
    ctx : dict
        Context as returned by ``make_ctx``.
    reps : int
        Number of timing repetitions for an equivalent candidate.

    Returns
    -------
    dict
        Result row with the verdict (REJECTED_STATIC, REJECTED_NOT_EQUIVALENT, EQUIVALENT_NOT_FASTER or
        ACCEPTED), whether it was flagged as not equivalent, details and, if timed, the timing statistics.
    """
    row = {"case": case.name, "candidate": cand.name, "expected": cand.expected, "fault": cand.fault}
    ok, msg = static_check(cand.sql)
    if not ok:
        return {**row, "verdict": "REJECTED_STATIC", "flagged_not_equivalent": True, "detail": msg}
    states, detail = [], []
    for label, p in case.params(ctx):
        try:
            key = (case.name, label)
            if key not in CACHE:  # originele uitvoer maar een keer berekenen
                CACHE[key] = run_query(conn, case.original, p, timeout_ms=TIMEOUT_MS)
            o = CACHE[key]
            c = run_query(conn, cand.sql, p, timeout_ms=TIMEOUT_MS)
        except psycopg.Error as e:
            states.append("EXEC_ERROR")
            detail.append(f"{label}: {type(e).__name__}")
            continue
        cmp = compare(o, c, case.order_cols)
        states.append(cmp.status)
        if cmp.status not in {"EQUIVALENT"}:
            detail.append(f"{label}: {cmp.status} {cmp.detail}")
    all_ok = all(s in OK_STATES for s in states)
    out = {**row, "param_sets": len(states), "failing_param_sets": sum(s not in OK_STATES for s in states),
           "flagged_not_equivalent": not all_ok, "detail": "; ".join(detail)[:300]}
    if all_ok:
        t = measure(conn, case.original, cand.sql, case.timing_params(ctx), reps=reps)
        out.update(t)
        out["verdict"] = "ACCEPTED" if t["faster"] else "EQUIVALENT_NOT_FASTER"
    else:
        out["verdict"] = "REJECTED_NOT_EQUIVALENT"
    return out


def main():
    """
    Run the validation framework on all candidates, print the summary and save the results to ``results/``.

    Command-line arguments: ``uri`` (database URI) and ``--reps`` (timing repetitions, default 7).

    Returns
    -------
    None
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("uri")
    ap.add_argument("--reps", type=int, default=7)
    args = ap.parse_args()
    conn = psycopg.connect(args.uri, autocommit=True)
    ctx = make_ctx(conn)
    results = []
    for case in CASES:
        for cand in case.candidates:
            assert cand.sql.strip() != case.original.strip(), f"{cand.name}: kandidaat is gelijk aan origineel (replace mislukt?)"
        for cand in case.candidates:
            r = evaluate(conn, case, cand, ctx, args.reps)
            results.append(r)
            print(f"{case.name:15} {cand.name:42} verwacht={cand.expected:15} -> {r['verdict']:24} {r.get('speedup','')}")
    # samenvatting
    neq = [r for r in results if r["expected"] == "not_equivalent"]
    eq = [r for r in results if r["expected"] == "equivalent"]
    detected = sum(r["flagged_not_equivalent"] for r in neq)
    false_rej = sum(r["flagged_not_equivalent"] for r in eq)
    print(f"\nFout (niet-gelijkwaardig) gedetecteerd: {detected}/{len(neq)}")
    print(f"Foute afkeuringen van gelijkwaardige kandidaten: {false_rej}/{len(eq)}")
    missed = [r["candidate"] for r in neq if not r["flagged_not_equivalent"]]
    print("Gemist:", missed or "geen")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = ROOT / "results"
    out.mkdir(exist_ok=True)
    (out / f"validation-{stamp}.json").write_text(json.dumps(results, indent=2, default=str))
    keys = sorted({k for r in results for k in r})
    with open(out / f"validation-{stamp}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(results)
    print("opgeslagen in", out / f"validation-{stamp}.csv")


if __name__ == "__main__":
    main()
