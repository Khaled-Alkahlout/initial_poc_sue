"""Laat een LLM de originele query's herschrijven onder vier contextcondities en beoordeel elke uitvoer
met hetzelfde validatieframework als run_validation.py.

Gebruik:
  python scripts/run_llm.py <db-uri> --dry-run                 # alleen prompts bouwen en opslaan, geen API
  python scripts/run_llm.py <db-uri> --model mock --reps 1     # hele keten testen zonder API (origineel terug)
  python scripts/run_llm.py <db-uri> --model claude-sonnet-5-5 --reps 3 --val-reps 5
  python scripts/run_llm.py --selection-only --top-k 1       # offline JSON; geen DB, API of bestanden
  python scripts/run_llm.py <db-uri> --select-mock --top-k 1 # selectie voor contextopbouw

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

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cases.cases import CASES, make_ctx  # noqa: E402
from cases.classes.candidate import Candidate  # noqa: E402
from llm.client import SYSTEM, build_prompt, call_llm, extract_sql  # noqa: E402
from llm.context import CONDITIONS, build_context  # noqa: E402
from query_selection.adapters import mock_telemetry, selected_cases  # noqa: E402
from query_selection.policy import SelectionPolicy  # noqa: E402
from query_selection.selection import select_queries  # noqa: E402


def main(argv: list[str] | None = None):
    """
    Let an LLM rewrite the original queries under the four context conditions and validate every output.

    Existing experiment options remain unchanged. ``--selection-only`` returns
    mock selection JSON before database imports or file creation. ``--select-mock``
    passes ranked original Case objects to the same context/model/validation loop.
    Pipeline artifacts are saved in ``results/llm-<timestamp>/``.

    Returns
    -------
    None
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("uri", nargs="?", help="verplicht behalve bij --selection-only")
    ap.add_argument("--model", default="claude-sonnet-5-5", help="Anthropic-modelnaam, of 'mock'")
    ap.add_argument("--reps", type=int, default=3, help="LLM-aanroepen per query per conditie")
    ap.add_argument("--val-reps", type=int, default=7, help="tijdmetingen per gelijkwaardige kandidaat (3 gaf valse ACCEPTED in de A/A-test)")
    ap.add_argument("--cases", nargs="*", default=[c.name for c in CASES])
    ap.add_argument("--conditions", nargs="*", default=CONDITIONS, choices=CONDITIONS)
    ap.add_argument("--dry-run", action="store_true", help="alleen prompts opslaan, geen LLM en geen validatie")
    ap.add_argument("--select-mock", action="store_true", help="filter en rank met expliciet gesimuleerde workloadcijfers")
    ap.add_argument("--selection-only", action="store_true", help="mockselectie als JSON naar stdout; geen DB, netwerk of bestanden")
    ap.add_argument("--top-k", type=int, help="maximum aantal geselecteerde queries; vereist selectiemodus")
    ap.add_argument("--exclude-query", action="append", default=[], help="query-ID uitsluiten; herhaalbaar")
    ap.add_argument("--exclude-schema", action="append", default=[], help="extra schema uitsluiten; herhaalbaar")
    ap.add_argument("--exclude-table", action="append", default=[], help="tabel of schema.tabel uitsluiten; herhaalbaar")
    args = ap.parse_args(argv)

    selection_enabled = args.select_mock or args.selection_only
    if not selection_enabled and (args.top_k is not None or args.exclude_query or args.exclude_schema or args.exclude_table):
        ap.error("selectieopties vereisen --select-mock of --selection-only")
    if not args.selection_only and not args.uri:
        ap.error("uri is verplicht behalve bij --selection-only")
    cases_to_run = [case for case in CASES if case.name in args.cases]
    selection = None
    if selection_enabled:
        unknown = sorted(set(args.cases) - {case.name for case in CASES})
        if unknown:
            ap.error("onbekende cases: " + ", ".join(unknown))
        try:
            policy = SelectionPolicy(
                top_k=args.top_k,
                excluded_query_ids=frozenset(args.exclude_query),
                excluded_schemas=SelectionPolicy().excluded_schemas | frozenset(args.exclude_schema),
                excluded_tables=frozenset(args.exclude_table),
            )
        except ValueError as exc:
            ap.error(str(exc))
        selection = select_queries(mock_telemetry(cases_to_run), policy)
        cases_to_run = selected_cases(selection, cases_to_run)
        if args.selection_only or not cases_to_run:
            print(json.dumps(selection.to_dict(), indent=2, ensure_ascii=False, allow_nan=False))
            return

    # Database/validator dependencies are deliberately absent from the offline path.
    import psycopg
    from scripts.run_validation import evaluate

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = ROOT / "results" / f"llm-{stamp}"
    (out / "prompts").mkdir(parents=True)
    (out / "responses").mkdir()
    (out / "prompts" / "_system.txt").write_text(SYSTEM, encoding="utf-8")
    if selection is not None:
        (out / "selection.json").write_text(
            json.dumps(selection.to_dict(), indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    decisions_by_id = {d.telemetry.query_id: d for d in selection.selected} if selection else {}

    conn = psycopg.connect(args.uri, autocommit=True)
    ctx = make_ctx(conn)
    results = []
    for case in cases_to_run:
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
                if case.name in decisions_by_id:
                    decision = decisions_by_id[case.name]
                    r.update({"query_id": case.name, "selection_rank": decision.rank,
                              "workload_impact_ms": decision.impact_ms,
                              "telemetry_source": decision.telemetry.source,
                              "telemetry_is_synthetic": decision.telemetry.is_synthetic,
                              "telemetry_window_id": decision.telemetry.window_id})
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
