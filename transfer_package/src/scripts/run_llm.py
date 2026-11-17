"""Laat een LLM de originele query's herschrijven onder vier contextcondities en beoordeel elke uitvoer
met hetzelfde validatieframework als run_validation.py.

Gebruik:
  python scripts/run_llm.py <db-uri> --dry-run                 # alleen prompts bouwen en opslaan, geen API
  python scripts/run_llm.py <db-uri> --model mock --reps 3     # A/A-controle: de hele keten zonder API (origineel terug)
  python scripts/run_llm.py <db-uri> --reps 3 --val-reps 7     # OpenRouter, anthropic/claude-sonnet-5.5 (standaard)
  python scripts/run_llm.py <db-uri> --model anthropic/claude-haiku-5.5 \
         --effort medium --max-tokens 2000 --conditions C1_query C4_stats
  python scripts/run_llm.py <db-uri> --provider anthropic --model claude-sonnet-5-5   # direct, met ANTHROPIC_API_KEY

Uitvoer: results/llm-<tijdstempel>/ (of de map van --out) met meta.json, prompts/, responses/ en
llm-results.csv/.json en resultaten.csv (Nederlandse kolommen, voor Excel). Er wordt niets overschreven.
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
from llm.client import PROVIDERS, SQL_BLOCK, SYSTEM, build_prompt, call_llm, extract_sql  # noqa: E402
from llm.context import CONDITIONS, build_context  # noqa: E402
from llm.uitvoer import schrijf_resultaten_csv  # noqa: E402
from scripts.run_validation import evaluate  # noqa: E402

EFFORTS = ["low", "medium", "high", "xhigh", "max"]


def main():
    """
    Let an LLM rewrite the original queries under the context conditions and validate every output.

    Command-line arguments: ``uri``, ``--model``, ``--provider``, ``--effort``, ``--max-tokens``, ``--reps``,
    ``--val-reps``, ``--cases``, ``--conditions``, ``--out``, ``--label`` and ``--dry-run``. Prompts, responses,
    the settings (meta.json) and result tables are saved in the output folder.

    Verdicts besides those of the validator: "TRUNCATED" (the answer was cut off by the token limit before a
    complete SQL block was written; not validated) and "API_ERROR" (the call failed after retries; not validated).

    Returns
    -------
    None
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("uri")
    ap.add_argument("--model", default="anthropic/claude-sonnet-5.5",
                    help="modelnaam van de provider (bij openrouter: anthropic/claude-...), of 'mock'")
    ap.add_argument("--provider", default="openrouter", choices=PROVIDERS,
                    help="openrouter (OPENROUTER_API_KEY, standaard) of anthropic (ANTHROPIC_API_KEY, direct)")
    ap.add_argument("--effort", default=None, choices=EFFORTS,
                    help="denkinspanning; zonder waarde geldt de standaard van het model (verschilt per model)")
    ap.add_argument("--max-tokens", type=int, default=4000,
                    help="harde limiet op uitvoertokens, inclusief denktokens")
    ap.add_argument("--reps", type=int, default=3, help="LLM-aanroepen per query per conditie")
    ap.add_argument("--val-reps", type=int, default=7, help="tijdmetingen per gelijkwaardige kandidaat (3 gaf valse ACCEPTED in de A/A-test)")
    ap.add_argument("--cases", nargs="*", default=[c.name for c in CASES])
    ap.add_argument("--conditions", nargs="*", default=CONDITIONS, choices=CONDITIONS)
    ap.add_argument("--out", default=None, help="uitvoermap (standaard results/llm-<tijdstempel>); mag nog niet bestaan")
    ap.add_argument("--label", default="", help="vrije tekst die in meta.json wordt bewaard")
    ap.add_argument("--dry-run", action="store_true", help="alleen prompts opslaan, geen LLM en geen validatie")
    args = ap.parse_args()
    if args.provider == "openrouter" and args.model != "mock" and "/" not in args.model:
        ap.error("bij --provider openrouter is een volledige modelnaam nodig, bijvoorbeeld anthropic/claude-sonnet-5.5 "
                 "(of kies --provider anthropic voor een directe Anthropic-sleutel)")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out = Path(args.out) if args.out else ROOT / "results" / f"llm-{stamp}"
    if not out.is_absolute():
        out = ROOT / out
    (out / "prompts").mkdir(parents=True)
    (out / "responses").mkdir()
    (out / "prompts" / "_system.txt").write_text(SYSTEM, encoding="utf-8")
    (out / "meta.json").write_text(json.dumps({
        "model": args.model, "provider": args.provider, "effort": args.effort, "max_tokens": args.max_tokens,
        "reps": args.reps, "val_reps": args.val_reps, "cases": args.cases, "conditions": args.conditions,
        "label": args.label, "started": datetime.now().isoformat(timespec="seconds"), "dry_run": args.dry_run,
    }, indent=2), encoding="utf-8")

    conn = psycopg.connect(args.uri, autocommit=True)
    ctx = make_ctx(conn)
    results = []
    partial = out / "llm-results.partial.jsonl"
    for case in [c for c in CASES if c.name in args.cases]:
        for cond in args.conditions:
            prompt = build_prompt(build_context(conn, case, ctx, cond))
            (out / "prompts" / f"{case.name}__{cond}.txt").write_text(prompt, encoding="utf-8")
            if args.dry_run:
                print(f"{case.name:15} {cond:10} prompt: {len(prompt)} tekens")
                continue
            for rep in range(1, args.reps + 1):
                tag = f"{case.name}__{cond}__r{rep}"
                base = {"condition": cond, "rep": rep, "model": args.model, "provider": args.provider,
                        "effort": args.effort or "", "max_tokens": args.max_tokens}
                try:
                    resp = call_llm(prompt, args.model, max_tokens=args.max_tokens, original_sql=case.original,
                                    provider=args.provider, effort=args.effort)
                except Exception as e:  # netwerk- of API-fout: noteren en doorgaan; een ontbrekende sleutel stopt wel (SystemExit)
                    err = f"{type(e).__name__}: {str(e)[:300]}"
                    (out / "responses" / f"{tag}.json").write_text(
                        json.dumps({"error": err, "text": "", "sql": "", "model": args.model}, indent=2, ensure_ascii=False),
                        encoding="utf-8")
                    r = {"case": case.name, "candidate": f"LLM_{cond}_r{rep}", "verdict": "API_ERROR", "detail": err,
                         "unchanged": False, "input_tokens": 0, "output_tokens": 0, "llm_seconds": 0,
                         "stop_reason": "error", **base}
                    results.append(r)
                    _append(partial, r)
                    print(f"{case.name:15} {cond:10} r{rep}  -> API_ERROR  {err[:100]}")
                    continue
                sql = extract_sql(resp["text"])
                (out / "responses" / f"{tag}.json").write_text(
                    json.dumps({**resp, "sql": sql, "model": args.model}, indent=2, ensure_ascii=False), encoding="utf-8")
                unchanged = sql.strip() == case.original.strip()
                truncated = resp["stop_reason"] == "max_tokens" and not SQL_BLOCK.search(resp["text"])
                if truncated:  # afgekapt voordat er een volledig SQL-blok stond: niets om te valideren
                    r = {"case": case.name, "candidate": f"LLM_{cond}_r{rep}", "verdict": "TRUNCATED",
                         "detail": "afgekapt door de tokenlimiet voor een volledig SQL-blok"}
                else:
                    cand = Candidate(f"LLM_{cond}_r{rep}", sql, "unknown", "llm")
                    r = evaluate(conn, case, cand, ctx, args.val_reps)
                r.update({**base, "unchanged": unchanged, "input_tokens": resp["input_tokens"],
                          "output_tokens": resp["output_tokens"], "llm_seconds": resp["seconds"],
                          "stop_reason": resp["stop_reason"], "cost_reported": resp.get("cost_reported") or ""})
                results.append(r)
                _append(partial, r)
                print(f"{case.name:15} {cond:10} r{rep}  -> {r['verdict']:24} {r.get('speedup', '')}"
                      + ("  (ongewijzigd)" if unchanged else "") + (f"  [{resp['stop_reason']}]" if truncated else ""))
    if args.dry_run:
        print("prompts opgeslagen in", out / "prompts")
        return

    (out / "llm-results.json").write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    keys = sorted({k for r in results for k in r})
    with open(out / "llm-results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(results)

    # samenvatting per conditie
    print(f"\n{'conditie':10} {'n':>3} {'statisch':>9} {'fout':>5} {'gelijk,niet sneller':>20} {'ACCEPTED':>9} "
          f"{'afgekapt':>9} {'api-fout':>9} {'mediaan speedup (acc.)':>23}")
    by = defaultdict(list)
    for r in results:
        by[r["condition"]].append(r)
    for cond in args.conditions:
        rs = by[cond]
        cnt = lambda v: sum(r["verdict"] == v for r in rs)
        acc = [r["speedup"] for r in rs if r["verdict"] == "ACCEPTED" and r.get("speedup")]
        print(f"{cond:10} {len(rs):>3} {cnt('REJECTED_STATIC'):>9} {cnt('REJECTED_NOT_EQUIVALENT'):>5} "
              f"{cnt('EQUIVALENT_NOT_FASTER'):>20} {cnt('ACCEPTED'):>9} {cnt('TRUNCATED'):>9} {cnt('API_ERROR'):>9} "
              f"{(round(median(acc), 2) if acc else '-'):>23}")
    print("opgeslagen in", out)
    print("leesbaar resultaat (Nederlandse kolommen):", schrijf_resultaten_csv(out))


def _append(path: Path, row: dict) -> None:
    """
    Append one result row to a JSON-lines file, so a crash does not lose the answers that were already judged.

    Parameters
    ----------
    path : Path
        The ``.jsonl`` file.
    row : dict
        Result row.

    Returns
    -------
    None
    """
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


if __name__ == "__main__":
    main()
