"""Laat een LLM de originele query's herschrijven onder vier contextcondities en beoordeel elke uitvoer
met hetzelfde validatieframework als run_validation.py.

Gebruik:
  python scripts/run_llm.py <db-uri> --dry-run                 # alleen prompts bouwen en opslaan, geen API
  python scripts/run_llm.py <db-uri> --model mock --reps 1     # hele keten testen zonder API (origineel terug)
  python scripts/run_llm.py <db-uri> --model claude-sonnet-5-5 --reps 3 --val-reps 5

Uitvoer: results/llm-<tijdstempel>/ met prompts/, responses/ en llm-results.csv/.json. Er wordt niets overschreven.
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cases.cases import CASES, make_ctx  # noqa: E402
from cases.classes.candidate import Candidate  # noqa: E402
from llm.client import SYSTEM, build_prompt, call_llm, extract_sql  # noqa: E402
from llm.context import CONDITIONS, build_context  # noqa: E402
from scripts.run_validation import evaluate  # noqa: E402


def main():
    """
    Let an LLM rewrite the original queries under the four context conditions and validate every output.

    Command-line arguments: ``uri``, ``--model``, ``--reps``, ``--val-reps``, ``--cases``, ``--conditions``
    and ``--dry-run``. Prompts, responses and result tables are saved in ``results/llm-<timestamp>/``.

    Returns
    -------
    None
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("uri")
    ap.add_argument("--model", default="claude-sonnet-5-5", help="Anthropic-modelnaam, of 'mock'")
    ap.add_argument("--reps", type=int, default=3, help="LLM-aanroepen per query per conditie")
    ap.add_argument("--val-reps", type=int, default=7, help="tijdmetingen per gelijkwaardige kandidaat (3 gaf valse ACCEPTED in de A/A-test)")
    ap.add_argument("--cases", nargs="*", default=[c.name for c in CASES])
    ap.add_argument("--conditions", nargs="*", default=CONDITIONS, choices=CONDITIONS)
    ap.add_argument("--dry-run", action="store_true", help="alleen prompts opslaan, geen LLM en geen validatie")
    args = ap.parse_args()

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = ROOT / "results" / f"llm-{stamp}"
    (out / "prompts").mkdir(parents=True)
    (out / "responses").mkdir()
    (out / "prompts" / "_system.txt").write_text(SYSTEM, encoding="utf-8")

    conn = psycopg.connect(args.uri, autocommit=True)
    ctx = make_ctx(conn)
    results = []
    for case in [c for c in CASES if c.name in args.cases]:
        for cond in args.conditions:
            prompt = build_prompt(build_context(conn, case, ctx, cond))
            (out / "prompts" / f"{case.name}__{cond}.txt").write_text(prompt, encoding="utf-8")
            if args.dry_run:
                print(f"{case.name:15} {cond:10} prompt: {len(prompt)} tekens")
                continue
            for rep in range(1, args.reps + 1):
                resp = call_llm(prompt, args.model, original_sql=case.original)
                sql = extract_sql(resp["text"])
                tag = f"{case.name}__{cond}__r{rep}"
                (out / "responses" / f"{tag}.json").write_text(
                    json.dumps({**resp, "sql": sql, "model": args.model}, indent=2, ensure_ascii=False), encoding="utf-8")
                cand = Candidate(f"LLM_{cond}_r{rep}", sql, "unknown", "llm")
                unchanged = sql.strip() == case.original.strip()
                r = evaluate(conn, case, cand, ctx, args.val_reps)
                r.update({"condition": cond, "rep": rep, "model": args.model, "unchanged": unchanged,
                          "input_tokens": resp["input_tokens"], "output_tokens": resp["output_tokens"],
                          "llm_seconds": resp["seconds"]})
                results.append(r)
                print(f"{case.name:15} {cond:10} r{rep}  -> {r['verdict']:24} {r.get('speedup', '')}"
                      + ("  (ongewijzigd)" if unchanged else ""))
    if args.dry_run:
        print("prompts opgeslagen in", out / "prompts")
        return

    (out / "llm-results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    keys = sorted({k for r in results for k in r})
    with open(out / "llm-results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(results)

    # samenvatting per conditie: dit is de kern van de onderzoeksvraag
    print(f"\n{'conditie':10} {'n':>3} {'statisch':>9} {'fout':>5} {'gelijk,niet sneller':>20} {'ACCEPTED':>9} {'mediaan speedup (acc.)':>23}")
    by = defaultdict(list)
    for r in results:
        by[r["condition"]].append(r)
    for cond in args.conditions:
        rs = by[cond]
        cnt = lambda v: sum(r["verdict"] == v for r in rs)
        acc = [r["speedup"] for r in rs if r["verdict"] == "ACCEPTED" and r.get("speedup")]
        print(f"{cond:10} {len(rs):>3} {cnt('REJECTED_STATIC'):>9} {cnt('REJECTED_NOT_EQUIVALENT'):>5} "
              f"{cnt('EQUIVALENT_NOT_FASTER'):>20} {cnt('ACCEPTED'):>9} {(round(median(acc), 2) if acc else '-'):>23}")
    print("opgeslagen in", out)


if __name__ == "__main__":
    main()
