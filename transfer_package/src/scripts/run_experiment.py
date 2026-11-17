"""Draai het modelvergelijkingsexperiment: dezelfde query's, dezelfde database en dezelfde validatie voor meerdere
modellen en meerdere limieten op het aantal uitvoertokens.

Het raster is: modellen x outputlimieten x (query's x condities x herhalingen). Elk model-limietpaar is een eigen
run van run_llm.py in results/experiment-<naam>/<model>_<limiet>/. Is een run klaar (llm-results.csv bestaat), dan
wordt hij bij een volgende start overgeslagen, zodat je na een onderbreking gewoon opnieuw kunt starten.

Gebruik (sleutel alleen in de terminal zetten, nooit in een bestand):
  python scripts/run_experiment.py --check                       # sleutel en modelnamen testen, geen database nodig
  python scripts/run_experiment.py <db-uri> --plan               # alleen het plan en een kostenschatting tonen
  python scripts/run_experiment.py <db-uri>                      # het hele experiment
  python scripts/run_experiment.py <db-uri> --models haiku sonnet --limits 2000

Standaard: OpenRouter, effort medium voor alle modellen, limieten 4000 2000 1000, condities C1_query en C4_stats,
alle vier de query's en 3 herhalingen.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cases.cases import CASES  # noqa: E402
from llm.client import PROVIDERS, call_llm  # noqa: E402
from llm.context import CONDITIONS  # noqa: E402
from llm.prices import ORDER, cost_usd, family  # noqa: E402
from llm.uitvoer import voeg_samen  # noqa: E402

MODEL_IDS = {
    "openrouter": {"haiku": "anthropic/claude-haiku-5.5", "sonnet": "anthropic/claude-sonnet-5.5",
                   "opus": "anthropic/claude-opus-5.5", "fable": "anthropic/claude-fable-5.1"},
    "anthropic": {"haiku": "claude-haiku-5-5", "sonnet": "claude-sonnet-5-5",
                  "opus": "claude-opus-5-5", "fable": "claude-fable-5-1"},
}
# Gemiddelde tokens per antwoord uit de Sonnet-run (map results/llm-2026102*): invoer C1 776, C4 4462; uitvoer circa 1060.
EST_TOKENS = {"C1_query": (776, 1036), "C2_schema": (1740, 1075), "C3_plan": (2827, 1042), "C4_stats": (4462, 1093)}
SECONDS_PER_ANSWER = 35  # schatting uit de tijdstempels van de eerdere runs, inclusief validatie


def resolve(models: list[str], provider: str) -> dict[str, str]:
    """
    Resolve model names given on the command line to ids of the provider.

    Parameters
    ----------
    models : list of str
        Family keys ("haiku", "sonnet", "opus", "fable") or literal model ids (anything with a "/" or "claude").
    provider : str
        "openrouter" or "anthropic".

    Returns
    -------
    dict
        Mapping from a short key (used in folder names) to the model id.
    """
    out = {}
    for m in models:
        if m in MODEL_IDS[provider]:
            out[m] = MODEL_IDS[provider][m]
        else:
            out[re.sub(r"[^a-z0-9]+", "-", m.lower()).strip("-")] = m
    return out


def plan_runs(models: dict[str, str], limits: list[int], exp_dir: Path) -> list[dict]:
    """
    Build the list of runs: one per model and output limit, cheap models first.

    Parameters
    ----------
    models : dict
        Short key to model id.
    limits : list of int
        Output token limits.
    exp_dir : Path
        Experiment folder.

    Returns
    -------
    list of dict
        Each with "key", "model", "limit" and "folder".
    """
    keys = sorted(models, key=lambda k: ORDER.index(family(k)) if family(k) in ORDER else 99)
    return [{"key": k, "model": models[k], "limit": lim, "folder": exp_dir / f"{k}_{lim}"} for k in keys for lim in limits]


def estimate(model: str, conditions: list[str], n_cases: int, reps: int) -> float | None:
    """
    Estimate the cost of one run from the average token counts of the earlier Sonnet run.

    Parameters
    ----------
    model : str
        Model id.
    conditions : list of str
        Conditions in the run.
    n_cases : int
        Number of queries.
    reps : int
        Repetitions per query and condition.

    Returns
    -------
    float or None
        Estimated dollars; None for an unknown model. Models that think more than Sonnet cost more than this.
    """
    total = 0.0
    for c in conditions:
        i, o = EST_TOKENS[c]
        cost = cost_usd(model, i, o)
        if cost is None:
            return None
        total += cost * n_cases * reps
    return total


def check(models: dict[str, str], provider: str, effort: str | None) -> int:
    """
    Send one tiny request to every model to test the key, the model names and the effort setting.

    Parameters
    ----------
    models : dict
        Short key to model id.
    provider : str
        Provider name.
    effort : str or None
        Effort level to test.

    Returns
    -------
    int
        Number of models that failed.
    """
    bad = 0
    for k, mid in models.items():
        try:
            r = call_llm("Antwoord met alleen het woord: klaar", mid, max_tokens=1000, provider=provider, effort=effort)
            c = cost_usd(mid, r["input_tokens"], r["output_tokens"])
            print(f"OK    {mid:36} stop={r['stop_reason']:11} in={r['input_tokens']:>4} uit={r['output_tokens']:>4} "
                  f"{r['seconds']:>5}s  kosten~${(c or 0):.5f}  gerapporteerd={r.get('cost_reported')}  antwoord={r['text'].strip()[:30]!r}")
        except Exception as e:  # noqa: BLE001
            bad += 1
            print(f"FOUT  {mid:36} {type(e).__name__}: {str(e)[:200]}")
    return bad


def main():
    """
    Run, resume or plan the model-comparison experiment.

    Returns
    -------
    None
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("uri", nargs="?", help="database-URI (niet nodig bij --check)")
    ap.add_argument("--name", default="modelvergelijking", help="naam van de experimentmap results/experiment-<naam>")
    ap.add_argument("--provider", default="openrouter", choices=PROVIDERS)
    ap.add_argument("--models", nargs="*", default=["haiku", "sonnet", "opus", "fable"],
                    help="haiku sonnet opus fable, of letterlijke model-id's van de provider")
    ap.add_argument("--limits", nargs="*", type=int, default=[4000, 2000, 1000], help="limieten op uitvoertokens")
    ap.add_argument("--effort", default="medium", choices=["low", "medium", "high", "xhigh", "max"],
                    help="gelijk voor alle modellen, zodat alleen het model verschilt")
    ap.add_argument("--conditions", nargs="*", default=["C1_query", "C4_stats"], choices=CONDITIONS)
    ap.add_argument("--cases", nargs="*", default=[c.name for c in CASES])
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--val-reps", type=int, default=7)
    ap.add_argument("--check", action="store_true", help="test sleutel en modelnamen met een klein verzoek per model en stop")
    ap.add_argument("--plan", action="store_true", help="toon het plan en de kostenschatting en stop")
    args = ap.parse_args()

    models = resolve(args.models, args.provider)
    if args.check:
        sys.exit(1 if check(models, args.provider, args.effort) else 0)
    if not args.uri:
        ap.error("de database-URI is verplicht (behalve bij --check)")

    exp_dir = ROOT / "results" / f"experiment-{args.name}"
    runs = plan_runs(models, args.limits, exp_dir)
    n_ans = len(args.cases) * len(args.conditions) * args.reps
    total = 0.0
    print(f"Experiment '{args.name}' via {args.provider}, effort {args.effort}; per run {n_ans} antwoorden "
          f"({len(args.cases)} query's x {len(args.conditions)} condities x {args.reps} herhalingen)")
    for r in runs:
        est = estimate(r["model"], args.conditions, len(args.cases), args.reps)
        total += est or 0
        done = (r["folder"] / "llm-results.csv").exists()
        print(f"  {'klaar ' if done else 'te doen'}  {r['model']:34} limiet {r['limit']:>5}   schatting ${(est or 0):.2f}")
    todo = [r for r in runs if not (r["folder"] / "llm-results.csv").exists()]
    print(f"Totaal {len(runs)} runs, {len(todo)} te doen, {len(todo) * n_ans} antwoorden; kosten circa ${total:.2f} "
          f"(schatting op basis van de tokens van Sonnet; modellen die meer denken kosten meer), "
          f"duur circa {len(todo) * n_ans * SECONDS_PER_ANSWER / 3600:.1f} uur")
    if args.plan:
        return

    exp_dir.mkdir(parents=True, exist_ok=True)
    settings = {"provider": args.provider, "models": models, "limits": args.limits, "effort": args.effort,
                "conditions": args.conditions, "cases": args.cases, "reps": args.reps, "val_reps": args.val_reps}
    sfile = exp_dir / "experiment.json"
    if sfile.exists():
        old = json.loads(sfile.read_text(encoding="utf-8"))
        old.pop("created", None)
        same_core = {k: old.get(k) for k in ("provider", "effort", "conditions", "cases", "reps", "val_reps")} == \
                    {k: settings[k] for k in ("provider", "effort", "conditions", "cases", "reps", "val_reps")}
        if not same_core:
            sys.exit(f"{sfile} bevat andere instellingen dan nu zijn opgegeven. Gebruik een andere --name, "
                     f"anders worden runs met verschillende instellingen gemengd.")
    else:
        sfile.write_text(json.dumps({**settings, "created": datetime.now().isoformat(timespec="seconds")}, indent=2),
                         encoding="utf-8")

    for i, r in enumerate(todo, 1):
        folder = r["folder"]
        if folder.exists():  # onderbroken run: nooit weggooien, wel opzij zetten
            folder.rename(folder.with_name(folder.name + datetime.now().strftime(".onvolledig-%Y%m%d-%H%M%S")))
        print(f"\n=== run {i}/{len(todo)}: {r['model']} limiet {r['limit']} ===", flush=True)
        t0 = time.time()
        cmd = [sys.executable, str(ROOT / "scripts" / "run_llm.py"), args.uri, "--provider", args.provider,
               "--model", r["model"], "--effort", args.effort, "--max-tokens", str(r["limit"]),
               "--conditions", *args.conditions, "--cases", *args.cases, "--reps", str(args.reps),
               "--val-reps", str(args.val_reps), "--out", str(folder), "--label", f"{args.name}|{r['key']}|{r['limit']}"]
        rc = subprocess.run(cmd).returncode
        res = folder / "llm-results.csv"
        if rc != 0 or not res.exists():
            sys.exit(f"Run mislukt (exitcode {rc}). Los het probleem op en start opnieuw; klaar gemelde runs blijven staan.")
        rows = list(csv.DictReader(open(res, encoding="utf-8")))
        errs = sum(x["verdict"] == "API_ERROR" for x in rows)
        print(f"run klaar in {(time.time() - t0) / 60:.1f} min; API-fouten: {errs}/{len(rows)}")
        if rows and errs / len(rows) > 0.25:
            folder.rename(folder.with_name(folder.name + ".api-fouten"))
            sys.exit("Meer dan 25% API-fouten: controleer sleutel, tegoed en modelnaam (zie --check). De run is opzij gezet als "
                     f"{folder.name}.api-fouten; na het oplossen start je gewoon opnieuw.")
    samen = voeg_samen(exp_dir)
    if samen:
        print("\nAlle runs samen, leesbaar (Nederlandse kolommen):", samen)
    print("\nKlaar. Analyseer met: python scripts/analyse_models.py --name", args.name)


if __name__ == "__main__":
    main()
