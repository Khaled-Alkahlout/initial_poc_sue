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
from cases.cases import CASES  # noqa: E402
from validator.evaluation import evaluate  # noqa: E402
from validator.timing import DEFAULT_REPETITIONS  # noqa: E402


def main():
    """
    Run the validation framework on all candidates, print the summary and save the results to ``results/``.

    Command-line arguments: ``uri`` (database URI) and ``--reps`` (timing repetitions, default 3, maximum 3 executed).

    Returns
    -------
    None
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("uri")
    ap.add_argument(
        "--reps", type=int, choices=range(1, 13), default=DEFAULT_REPETITIONS
    )
    args = ap.parse_args()
    results = []
    with psycopg.connect(args.uri, autocommit=True, connect_timeout=5) as conn:
        for case in CASES:
            for cand in case.candidates:
                assert cand.sql.strip() != case.original.strip(), (
                    f"{cand.name}: kandidaat is gelijk aan origineel (replace mislukt?)"
                )
                r = evaluate(conn, case, cand, reps=args.reps)
                results.append(r)
                print(
                    f"{case.name:15} {cand.name:42} verwacht={cand.expected:15} -> {r['verdict']:24} {r.get('speedup', '')}"
                )
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
    (out / f"validation-{stamp}.json").write_text(
        json.dumps(results, indent=2, default=str)
    )
    keys = sorted({k for r in results for k in r})
    with open(out / f"validation-{stamp}.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(results)
    print("opgeslagen in", out / f"validation-{stamp}.csv")


if __name__ == "__main__":
    main()
