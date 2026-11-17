"""Een leesbaar resultatenbestand met Nederlandse kolomnamen maken uit de technische bestanden van een run.

Een run (``results/llm-<tijdstempel>/``) bewaart zijn gegevens technisch: ``llm-results.json``, ``meta.json`` en
``responses/*.json``. De analysescripts en de Streamlit-demo lezen die bestanden. Dit bestand verandert daar niets aan:
het zet dezelfde gegevens om in ``resultaten.csv``, een tabel voor mensen met een regel per antwoord van het model.

Het bestand is gemaakt om in Excel te openen: scheidingsteken ``;``, decimale komma en UTF-8 met BOM.
Lees je het met pandas, gebruik dan ``pd.read_csv(pad, sep=";", decimal=",", encoding="utf-8-sig")``.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

from llm.prices import cost_usd
from validator.timing import SPEEDUP_THRESHOLD

NIET_OPGESLAGEN = "niet opgeslagen"  # oudere runs bewaarden provider, effort, limiet en stopreden niet

KOLOMMEN = [
    "query", "context", "herhaling",
    "model", "aanbieder", "effort", "max_uitvoertokens",
    "duur_origineel_ms", "duur_kandidaat_ms", "versnelling_x",
    "oordeel", "aantal_parametersets", "parametersets_met_verschil", "reden_afkeuring",
    "invoertokens", "uitvoertokens", "stopreden", "modeltijd_s", "kosten_usd", "query_ongewijzigd",
    "aantal_metingen", "spreiding_origineel_ms", "spreiding_kandidaat_ms",
    "sql_kandidaat",
]

CONTEXTEN = {"C1_query": "C1 query", "C2_schema": "C2 schema", "C3_plan": "C3 plan", "C4_stats": "C4 statistieken"}

OORDELEN = {
    "ACCEPTED": f"GOED: zelfde resultaat en minstens {str(SPEEDUP_THRESHOLD).replace('.', ',')}x sneller",
    "EQUIVALENT_NOT_FASTER": "ZELFDE RESULTAAT, NIET SNELLER",
    "REJECTED_NOT_EQUIVALENT": "AFGEKEURD: ANDER RESULTAAT",
    "REJECTED_STATIC": "AFGEKEURD: GEEN GELDIGE SELECT",
    "TRUNCATED": "AFGEKAPT DOOR DE TOKENLIMIET",
    "API_ERROR": "API-FOUT",
}

STOPREDENEN = {"end_turn": "klaar", "max_tokens": "tokenlimiet bereikt", "error": "fout"}


def _getal(x, decimalen: int = 0) -> str:
    """
    Format a number with a decimal comma, or return an empty string when there is no value.

    Parameters
    ----------
    x : int or float or str or None
        The value. None and "" give an empty string.
    decimalen : int, default 0
        Number of decimals.

    Returns
    -------
    str
        The formatted number, e.g. "205,8".
    """
    if x is None or x == "":
        return ""
    return f"{float(x):.{decimalen}f}".replace(".", ",")


def _instelling(rij: dict, meta: dict, sleutel: str) -> str:
    """
    Read a setting of a run (provider, effort, token limit) from the result row or else from ``meta.json``.

    Parameters
    ----------
    rij : dict
        Result row of one answer.
    meta : dict
        Content of ``meta.json`` (empty for runs that have none).
    sleutel : str
        Name of the setting.

    Returns
    -------
    str
        The value; "standaard" when it was left empty on purpose (the model default); "niet opgeslagen" when the
        run did not record the setting at all.
    """
    for bron in (rij, meta):
        if sleutel in bron:
            return str(bron[sleutel]) if bron[sleutel] not in (None, "") else "standaard"
    return NIET_OPGESLAGEN


def maak_rij(rij: dict, antwoord: dict, meta: dict) -> dict:
    """
    Translate one result row to a row with the Dutch columns of ``KOLOMMEN``.

    Parameters
    ----------
    rij : dict
        Result row from ``llm-results.json``.
    antwoord : dict
        The saved response of this answer (``responses/<query>__<context>__r<herhaling>.json``); empty if missing.
    meta : dict
        Content of ``meta.json`` of the run; empty for runs that have none.

    Returns
    -------
    dict
        Dutch column name to text value. Cells that do not apply (for example the timing of a rejected answer) are empty.
    """
    model = rij.get("model") or meta.get("model", "")
    tin, tuit = rij.get("input_tokens") or 0, rij.get("output_tokens") or 0
    gerapporteerd = rij.get("cost_reported") or antwoord.get("cost_reported")
    kosten = float(gerapporteerd) if gerapporteerd not in (None, "") else cost_usd(model, tin, tuit)
    stop = rij.get("stop_reason") or antwoord.get("stop_reason")
    uit = {
        "query": rij["case"],
        "context": CONTEXTEN.get(rij["condition"], rij["condition"]),
        "herhaling": rij["rep"],
        "model": model,
        "aanbieder": _instelling(rij, meta, "provider"),
        "effort": _instelling(rij, meta, "effort"),
        "max_uitvoertokens": _instelling(rij, meta, "max_tokens"),
        "duur_origineel_ms": _getal(rij.get("orig_median_ms"), 1),
        "duur_kandidaat_ms": _getal(rij.get("cand_median_ms"), 1),
        "versnelling_x": _getal(rij.get("speedup"), 2),
        "oordeel": OORDELEN.get(rij["verdict"], rij["verdict"]),
        "aantal_parametersets": rij.get("param_sets", ""),
        "parametersets_met_verschil": rij.get("failing_param_sets", ""),
        "reden_afkeuring": rij.get("detail", ""),
        "invoertokens": tin,
        "uitvoertokens": tuit,
        "stopreden": STOPREDENEN.get(stop, stop) if stop else NIET_OPGESLAGEN,
        "modeltijd_s": _getal(rij.get("llm_seconds"), 1),
        "kosten_usd": _getal(kosten, 5),
        "query_ongewijzigd": "ja" if str(rij.get("unchanged")) == "True" else "nee",
        "aantal_metingen": rij.get("reps", ""),
        "spreiding_origineel_ms": _getal(rij.get("orig_iqr_ms"), 1),
        "spreiding_kandidaat_ms": _getal(rij.get("cand_iqr_ms"), 1),
        "sql_kandidaat": antwoord.get("sql", ""),
    }
    return {k: uit[k] for k in KOLOMMEN}


def _schrijf(pad: Path, rijen: list[dict], kolommen: list[str]) -> None:
    """
    Write rows as a CSV that opens correctly in a Dutch Excel (semicolon, UTF-8 with BOM).

    Parameters
    ----------
    pad : Path
        The file to write.
    rijen : list of dict
        Rows with the keys in ``kolommen``.
    kolommen : list of str
        Column names, in the order of the file.

    Returns
    -------
    None
    """
    with open(pad, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=kolommen, delimiter=";")
        w.writeheader()
        w.writerows(rijen)


def schrijf_resultaten_csv(run_map) -> Path:
    """
    Write ``resultaten.csv`` in a run folder, built from its ``llm-results.json``, ``meta.json`` and ``responses/``.

    Parameters
    ----------
    run_map : str or Path
        A run folder such as ``results/llm-20261104-101500``.

    Returns
    -------
    Path
        The written ``resultaten.csv``.

    Raises
    ------
    FileNotFoundError
        When the folder has no ``llm-results.json`` (a run that is not finished).
    """
    run_map = Path(run_map)
    resultaten = json.loads((run_map / "llm-results.json").read_text(encoding="utf-8"))
    meta_pad = run_map / "meta.json"
    meta = json.loads(meta_pad.read_text(encoding="utf-8")) if meta_pad.exists() else {}
    rijen = []
    for r in resultaten:
        pad = run_map / "responses" / f"{r['case']}__{r['condition']}__r{r['rep']}.json"
        try:
            antwoord = json.loads(pad.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            antwoord = {}
        rijen.append(maak_rij(r, antwoord, meta))
    doel = run_map / "resultaten.csv"
    _schrijf(doel, rijen, KOLOMMEN)
    return doel


def voeg_samen(experiment_map) -> Path | None:
    """
    Combine the ``resultaten.csv`` of all finished runs of an experiment into one file with an extra column "run".

    A run that has ``llm-results.json`` but no ``resultaten.csv`` yet (made before this module existed) gets one first.
    Folders that were set aside (names with ".onvolledig" or ".api-fouten") and the "analyse" folder are skipped.

    Parameters
    ----------
    experiment_map : str or Path
        A folder ``results/experiment-<name>``.

    Returns
    -------
    Path or None
        The combined ``resultaten.csv`` in the experiment folder, or None when no run was finished.
    """
    experiment_map = Path(experiment_map)
    rijen = []
    for d in sorted(p for p in experiment_map.iterdir() if p.is_dir()):
        if d.name == "analyse" or ".onvolledig" in d.name or d.name.endswith(".api-fouten"):
            continue
        if not (d / "llm-results.json").exists():
            continue
        csv_pad = d / "resultaten.csv" if (d / "resultaten.csv").exists() else schrijf_resultaten_csv(d)
        with open(csv_pad, encoding="utf-8-sig", newline="") as f:
            rijen += [{"run": d.name, **r} for r in csv.DictReader(f, delimiter=";")]
    if not rijen:
        return None
    doel = experiment_map / "resultaten.csv"
    _schrijf(doel, rijen, ["run"] + KOLOMMEN)
    return doel
