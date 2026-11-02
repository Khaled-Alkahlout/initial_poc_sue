"""Analyse van de LLM-runs: wat leverde elke contextconditie op, en welke fouten kwamen voor?

Leest de mappen results/llm-*/ (llm-results.csv + responses/*.json), kiest zelf de volledige runs
(echt model, alle vier de condities; de proef en de A/A-controle met 'mock' vallen af) en schrijft naar results/analyse/:
  analyse.txt            alle tabellen als tekst (ook op het scherm)
  per_poging.csv         een rij per LLM-antwoord, met de uitkomst en de extra controles
  per_conditie.csv       samengevoegd over de casussen, met 95%-betrouwbaarheidsinterval
  per_casus_conditie.csv per casus en conditie
  voorbeelden.md         goede en foute antwoorden met de SQL en de uitleg van het model
  uitkomsten.png, speedup.png   figuren (alleen als matplotlib is geinstalleerd)

Uitkomstcategorieen (een per poging, in deze volgorde van voorrang):
  fout                 het framework keurde het antwoord af (niet gelijkwaardig of statisch afgekeurd)
  ongewijzigd          zelfde query als het origineel, na het weghalen van commentaar en witruimte
  ACCEPTED             gelijkwaardig en minstens de drempel sneller (SPEEDUP_THRESHOLD)
  gelijk, trager       gelijkwaardig maar langzamer dan 1/SPEEDUP_THRESHOLD
  gelijk, geen winst   gelijkwaardig, niet merkbaar sneller of trager

Gebruik: python scripts/analyse.py [--map results/llm-... results/llm-...]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cases.cases import CASES  # noqa: E402
from llm.context import CONDITIONS  # noqa: E402
from validator.timing import SPEEDUP_THRESHOLD  # noqa: E402

PRICE_IN, PRICE_OUT = 2.0, 10.0  # dollar per miljoen tokens (claude-sonnet-5-5)
CATS = ["ACCEPTED", "gelijk, geen winst", "ongewijzigd", "gelijk, trager", "fout"]
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
LIT_RE = re.compile(r"'((?:[^']|'')*)'")
ORIGINALS = {c.name: c.original for c in CASES}


def binom_cdf(k: int, n: int, p: float) -> float:
    """
    Cumulative binomial probability P(X <= k) for X ~ Binomial(n, p).

    Parameters
    ----------
    k : int
        Number of successes.
    n : int
        Number of trials.
    p : float
        Success probability.

    Returns
    -------
    float
        Probability of at most k successes.
    """
    return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(0, k + 1))


def clopper_pearson(k: int, n: int, alpha: float = 0.05) -> tuple[float, float]:
    """
    Exact (Clopper-Pearson) confidence interval for a proportion, found by bisection.

    Parameters
    ----------
    k : int
        Number of successes.
    n : int
        Number of trials.
    alpha : float, default 0.05
        Total error probability; 0.05 gives a 95% interval.

    Returns
    -------
    tuple of (float, float)
        Lower and upper bound of the interval; (nan, nan) when n is 0.
    """
    if n == 0:
        return float("nan"), float("nan")

    def solve(f, lo=0.0, hi=1.0):
        for _ in range(80):
            mid = (lo + hi) / 2
            if f(mid) > 0:
                hi = mid
            else:
                lo = mid
        return (lo + hi) / 2

    lower = 0.0 if k == 0 else solve(lambda p: (1 - binom_cdf(k - 1, n, p)) - alpha / 2)
    upper = 1.0 if k == n else solve(lambda p: alpha / 2 - binom_cdf(k, n, p))
    return lower, upper


def strip_comments(sql: str) -> str:
    """
    Remove SQL line comments (``-- ...``).

    Parameters
    ----------
    sql : str
        SQL text.

    Returns
    -------
    str
        SQL text without line comments.
    """
    return re.sub(r"--[^\n]*", "", sql)


def norm_sql(sql: str) -> str:
    """
    Normalise SQL text for an "is it the same query" comparison: no comments, one space, no trailing semicolon.

    Parameters
    ----------
    sql : str
        SQL text.

    Returns
    -------
    str
        Normalised SQL text.
    """
    return re.sub(r"\s+", " ", strip_comments(sql)).strip().rstrip(";").strip()


def literals(sql: str) -> set[str]:
    """
    Collect the string literals (between single quotes) in a query, ignoring comments.

    Parameters
    ----------
    sql : str
        SQL text.

    Returns
    -------
    set of str
        The literal values, without the quotes.
    """
    return set(LIT_RE.findall(strip_comments(sql)))


def classify(row: dict) -> str:
    """
    Assign the outcome category of one LLM attempt.

    Parameters
    ----------
    row : dict
        Attempt with the keys "verdict", "unchanged_norm" and "speedup" (float or None).

    Returns
    -------
    str
        One of CATS.
    """
    if row["verdict"].startswith("REJECTED"):
        return "fout"
    if row["unchanged_norm"]:
        return "ongewijzigd"
    if row["verdict"] == "ACCEPTED":
        return "ACCEPTED"
    if row["speedup"] is not None and row["speedup"] < 1 / SPEEDUP_THRESHOLD:
        return "gelijk, trager"
    return "gelijk, geen winst"


def fault_kind(row: dict) -> str:
    """
    Describe what went wrong in a rejected attempt, based on a comparison with the original query.

    Parameters
    ----------
    row : dict
        Attempt with the keys "sql", "case" and "verdict".

    Returns
    -------
    str
        A short description, or an empty string when the attempt was not rejected.
    """
    if not row["verdict"].startswith("REJECTED"):
        return ""
    new = sorted(literals(row["sql"]) - literals(ORIGINALS[row["case"]]))
    if new:
        return "waarde in de query die in het origineel niet staat: " + ", ".join(repr(x) for x in new)
    return "overig (resultaat verschilt van het origineel)"


def pick_folders(results: Path, explicit: list[str] | None) -> tuple[list[Path], list[Path]]:
    """
    Choose the result folders for the analysis and the A/A (mock) folders for the noise band.

    Parameters
    ----------
    results : Path
        The ``results`` folder of the kit.
    explicit : list of str or None
        Folders given on the command line; when None, all suitable folders are selected automatically.

    Returns
    -------
    tuple of (list of Path, list of Path)
        Full runs with a real model, and runs with the mock model.
    """
    full, mock = [], []
    candidates = [Path(x) for x in explicit] if explicit else sorted(results.glob("llm-*"))
    for d in candidates:
        f = d / "llm-results.csv"
        if not f.exists():
            continue
        rows = list(csv.DictReader(open(f, encoding="utf-8")))
        if not rows:
            continue
        if all(r["model"] == "mock" for r in rows):
            mock.append(d)
        elif {r["condition"] for r in rows} == set(CONDITIONS):
            full.append(d)
    return full, mock


def load_attempts(folders: list[Path]) -> list[dict]:
    """
    Read all attempts from the given folders and add the SQL, the explanation and the extra checks.

    Parameters
    ----------
    folders : list of Path
        Result folders with ``llm-results.csv`` and ``responses/``.

    Returns
    -------
    list of dict
        One dict per attempt: CSV columns plus "sql", "explanation", "unchanged_norm", "category",
        "new_literals", "uuid_in_sql" and "fault".
    """
    out = []
    for d in folders:
        for r in csv.DictReader(open(d / "llm-results.csv", encoding="utf-8")):
            tag = f"{r['case']}__{r['condition']}__r{r['rep']}"
            resp = json.load(open(d / "responses" / f"{tag}.json", encoding="utf-8"))
            orig = ORIGINALS[r["case"]]
            sql = resp["sql"]
            row = {
                "folder": d.name, "model": r["model"], "case": r["case"], "condition": r["condition"], "rep": int(r["rep"]),
                "verdict": r["verdict"], "speedup": float(r["speedup"]) if r.get("speedup") else None,
                "failing_param_sets": r.get("failing_param_sets", ""), "param_sets": r.get("param_sets", ""),
                "detail": r.get("detail", ""), "input_tokens": int(r["input_tokens"]),
                "output_tokens": int(r["output_tokens"]), "llm_seconds": float(r["llm_seconds"]),
                "sql": sql, "explanation": resp["text"].split("```")[-1].strip(),
                "unchanged_norm": norm_sql(sql) == norm_sql(orig),
                "new_literals": "|".join(sorted(literals(sql) - literals(orig))),
                "uuid_in_sql": bool(set(UUID_RE.findall(sql)) - set(UUID_RE.findall(orig))),
            }
            row["category"] = classify(row)
            row["fault"] = fault_kind(row)
            out.append(row)
    return out


def table(headers: list[str], rows: list[list], widths: list[int] | None = None) -> str:
    """
    Format rows as a fixed-width text table.

    Parameters
    ----------
    headers : list of str
        Column titles.
    rows : list of list
        Cell values; converted with ``str``.
    widths : list of int or None
        Column widths; computed from the content when None.

    Returns
    -------
    str
        The table as text, one line per row.
    """
    cells = [[str(c) for c in r] for r in rows]
    widths = widths or [max(len(h), *(len(r[i]) for r in cells)) for i, h in enumerate(headers)]
    line = lambda r: "  ".join(c.ljust(w) if i == 0 else c.rjust(w) for i, (c, w) in enumerate(zip(r, widths)))
    return "\n".join([line(headers), line(["-" * w for w in widths])] + [line(r) for r in cells])


def pct(k: int, n: int) -> str:
    """
    Format a proportion with its 95% Clopper-Pearson interval.

    Parameters
    ----------
    k : int
        Number of successes.
    n : int
        Number of trials.

    Returns
    -------
    str
        Text such as "25% [5-57]".
    """
    lo, hi = clopper_pearson(k, n)
    return f"{100 * k / n:.0f}% [{100 * lo:.0f}-{100 * hi:.0f}]"


def summarize(attempts: list[dict], mock_speedups: list[float]) -> tuple[str, list[dict], list[dict]]:
    """
    Compute all tables of the analysis.

    Parameters
    ----------
    attempts : list of dict
        Attempts as returned by ``load_attempts``.
    mock_speedups : list of float
        Speedups measured in the A/A control (mock model), used as the noise range.

    Returns
    -------
    tuple of (str, list of dict, list of dict)
        The report as text, the rows per condition and the rows per case and condition.
    """
    L = []
    n_tot = len(attempts)
    cases = [c.name for c in CASES if any(a["case"] == c.name for a in attempts)]
    L.append(f"ANALYSE LLM-RUNS: {n_tot} antwoorden, model {', '.join(sorted({a['model'] for a in attempts}))}")
    L.append(f"Mappen: {', '.join(sorted({a['folder'] for a in attempts}))}")
    L.append(f"Drempel ACCEPTED: speedup >= {SPEEDUP_THRESHOLD}; 'trager' = speedup < {1 / SPEEDUP_THRESHOLD:.2f}")
    if mock_speedups:
        L.append(f"Ruis A/A-controle ({len(mock_speedups)} metingen met het origineel): speedup {min(mock_speedups):.2f} tot {max(mock_speedups):.2f}")

    # 1. per conditie, samengevoegd
    L.append("\n1. PER CONDITIE (samengevoegd over de casussen; tussen haakjes het 95%-interval, exact)")
    cond_rows, rows = [], []
    for cond in CONDITIONS:
        rs = [a for a in attempts if a["condition"] == cond]
        c = Counter(a["category"] for a in rs)
        n = len(rs)
        cond_rows.append({"condition": cond, "n": n, **{k: c.get(k, 0) for k in CATS},
                          "fout_pct": pct(c["fout"], n), "ACCEPTED_pct": pct(c["ACCEPTED"], n),
                          "mean_input_tokens": round(sum(a["input_tokens"] for a in rs) / n),
                          "mean_output_tokens": round(sum(a["output_tokens"] for a in rs) / n),
                          "cost_usd": round(sum(a["input_tokens"] * PRICE_IN + a["output_tokens"] * PRICE_OUT for a in rs) / 1e6, 3)})
        rows.append([cond, n] + [c.get(k, 0) for k in CATS] + [pct(c["fout"], n), pct(c["ACCEPTED"], n)])
    L.append(table(["conditie", "n"] + CATS + ["fout [95%-int.]", "ACCEPTED [95%-int.]"], rows))

    L.append("\n2. KOSTEN EN LENGTE PER CONDITIE (prijs 2 en 10 dollar per miljoen tokens)")
    L.append(table(["conditie", "gem. invoertokens", "gem. uitvoertokens", "kosten (dollar)"],
                   [[r["condition"], r["mean_input_tokens"], r["mean_output_tokens"], r["cost_usd"]] for r in cond_rows]))
    L.append(f"Totaal: {sum(r['cost_usd'] for r in cond_rows):.3f} dollar")

    # 3. per casus x conditie
    L.append("\n3. PER CASUS EN CONDITIE (aantallen per categorie; mediaan speedup van de gelijkwaardige antwoorden)")
    cc_rows, rows = [], []
    short = {"ACCEPTED": "A", "gelijk, geen winst": "G", "ongewijzigd": "O", "gelijk, trager": "T", "fout": "F"}
    for case in cases:
        for cond in CONDITIONS:
            rs = [a for a in attempts if a["case"] == case and a["condition"] == cond]
            c = Counter(a["category"] for a in rs)
            sp = [a["speedup"] for a in rs if a["speedup"] is not None and a["category"] != "fout"]
            med = round(median(sp), 2) if sp else ""
            cc_rows.append({"case": case, "condition": cond, "n": len(rs), **{k: c.get(k, 0) for k in CATS}, "median_speedup": med})
            rows.append([case, cond, len(rs), " ".join(f"{short[k]}{c[k]}" for k in CATS if c[k]), med])
    L.append("A=ACCEPTED  G=gelijk, geen winst  O=ongewijzigd  T=gelijk, trager  F=fout")
    L.append(table(["casus", "conditie", "n", "uitkomsten", "mediaan speedup"], rows))

    # 4. fouten
    bad = [a for a in attempts if a["category"] == "fout"]
    L.append(f"\n4. FOUTEN ({len(bad)} van {n_tot})")
    L.append(table(["casus", "conditie", "rep", "param.sets fout", "wat ging er mis"],
                   [[a["case"], a["condition"], a["rep"], f"{a['failing_param_sets']}/{a['param_sets']}", a["fault"]] for a in bad]) if bad else "geen")

    # 5. extra controles
    L.append("\n5. EXTRA CONTROLES")
    uu = [a for a in attempts if a["uuid_in_sql"]]
    L.append(f"UUID uit de prompt hard-coded in de herschrijving: {len(uu)} van {n_tot}")
    for cond in CONDITIONS:
        rs = [a for a in attempts if a["condition"] == cond]
        L.append(f"  {cond}: {sum(a['uuid_in_sql'] for a in rs)}/{len(rs)}")
    L.append("Gelijkwaardig maar trager dan het origineel (zonder framework had je dit toegepast):")
    slow = [a for a in attempts if a["category"] == "gelijk, trager"]
    L.append(f"  {len(slow)} van {n_tot}" + (f", speedup {min(a['speedup'] for a in slow):.2f} tot {max(a['speedup'] for a in slow):.2f}" if slow else ""))
    return "\n".join(L), cond_rows, cc_rows


def write_examples(attempts: list[dict], path: Path) -> None:
    """
    Write good and bad examples (SQL and the model's own explanation) to a markdown file.

    Parameters
    ----------
    attempts : list of dict
        Attempts as returned by ``load_attempts``.
    path : Path
        Output file.

    Returns
    -------
    None
    """
    good, seen = [], set()
    for a in sorted((a for a in attempts if a["category"] == "ACCEPTED"), key=lambda a: -a["speedup"]):
        if a["condition"] not in seen and len(good) < 3:
            good.append(a)
            seen.add(a["condition"])
    bad = [a for a in attempts if a["category"] == "fout"][:3]
    slow = sorted((a for a in attempts if a["category"] == "gelijk, trager"), key=lambda a: a["speedup"])[:1]
    parts = ["# Voorbeelden uit de LLM-runs\n"]
    for title, group in (("Goede voorbeelden (ACCEPTED)", good), ("Foute voorbeelden (door het framework afgekeurd)", bad),
                         ("Gelijkwaardig maar trager", slow)):
        parts.append(f"\n## {title}\n")
        for a in group:
            parts.append(f"### {a['case']} / {a['condition']} / herhaling {a['rep']}  ->  {a['verdict']}"
                         + (f", speedup {a['speedup']}" if a["speedup"] else "") + "\n")
            if a["fault"]:
                parts.append(f"Wat ging er mis: {a['fault']}. Details: {a['detail'][:300]}\n")
            parts.append(f"Uitleg van het model: {a['explanation']}\n\n```sql\n{a['sql']}\n```\n")
    path.write_text("\n".join(parts), encoding="utf-8")


def write_csv(path: Path, rows: list[dict], skip: tuple = ()) -> None:
    """
    Write a list of dicts to a CSV file.

    Parameters
    ----------
    path : Path
        Output file.
    rows : list of dict
        Rows to write; the columns are the union of the keys.
    skip : tuple of str, default ()
        Keys that are left out.

    Returns
    -------
    None
    """
    keys = [k for k in dict.fromkeys(k for r in rows for k in r) if k not in skip]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def plot(attempts: list[dict], mock_speedups: list[float], outdir: Path) -> bool:
    """
    Draw the two figures: outcomes per case and condition, and speedup per attempt.

    Parameters
    ----------
    attempts : list of dict
        Attempts as returned by ``load_attempts``.
    mock_speedups : list of float
        Speedups of the A/A control; drawn as a grey noise band.
    outdir : Path
        Folder for ``uitkomsten.png`` and ``speedup.png``.

    Returns
    -------
    bool
        True when the figures were written, False when matplotlib is not installed.
    """
    try:
        import matplotlib
        import matplotlib.ticker
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
    except ImportError:
        return False
    colors = {"ACCEPTED": "#2a78d6", "gelijk, geen winst": "#b9b8b0", "ongewijzigd": "#e1e0da",
              "gelijk, trager": "#eb6834", "fout": "#6250d6"}
    ink, muted, surface = "#0b0b0b", "#52514e", "#fcfcfb"
    plt.rcParams.update({"font.size": 10, "axes.edgecolor": muted, "axes.labelcolor": muted, "xtick.color": muted,
                         "ytick.color": muted, "text.color": ink, "figure.facecolor": surface, "axes.facecolor": surface})
    cases = [c.name for c in CASES if any(a["case"] == c.name for a in attempts)]
    short = [c.split("_")[0] for c in CONDITIONS]
    legend = [Patch(facecolor=colors[k], edgecolor=surface, hatch="///" if k == "fout" else None, label=k) for k in CATS]

    fig, axes = plt.subplots(1, len(cases), figsize=(3 * len(cases) + 1, 4.2), sharey=True)
    for ax, case in zip(axes, cases):
        for i, cond in enumerate(CONDITIONS):
            rs = [a for a in attempts if a["case"] == case and a["condition"] == cond]
            c = Counter(a["category"] for a in rs)
            bottom = 0
            for k in CATS:
                if c[k]:
                    ax.bar(i, c[k], bottom=bottom, color=colors[k], edgecolor=surface, linewidth=2, width=0.62,
                           hatch="///" if k == "fout" else None)
                    ax.text(i, bottom + c[k] / 2, str(c[k]), ha="center", va="center", fontsize=9,
                            color="white" if k in ("ACCEPTED", "gelijk, trager", "fout") else ink,
                            bbox=dict(boxstyle="round,pad=0.2", fc=colors[k] if k != "fout" else "#4b3bb0", ec="none") if k == "fout" else None)
                    bottom += c[k]
        ax.set_title(case, fontsize=10, color=ink)
        ax.set_xticks(range(len(CONDITIONS)), short)
        ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(integer=True))
        ax.spines[["top", "right"]].set_visible(False)
        ax.yaxis.grid(True, color="#e6e5e0", linewidth=0.8)
        ax.set_axisbelow(True)
    axes[0].set_ylabel("aantal antwoorden")
    fig.suptitle("Uitkomst van elk LLM-antwoord per casus en contextconditie", x=0.01, ha="left", fontsize=12)
    fig.legend(handles=legend, loc="lower center", ncol=len(CATS), frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, 0.08, 1, 0.95))
    fig.savefig(outdir / "uitkomsten.png", dpi=200)
    plt.close(fig)

    fig, axes = plt.subplots(1, len(cases), figsize=(3 * len(cases) + 1, 4.2))
    for ax, case in zip(axes, cases):
        rs = [a for a in attempts if a["case"] == case and a["speedup"] is not None and a["category"] != "fout"]
        ys = [a["speedup"] for a in rs]
        if mock_speedups and ys and max(ys) < 20:
            ax.axhspan(min(mock_speedups), max(mock_speedups), color="#e6e5e0", zorder=0)
        for k in CATS:
            pts = [(CONDITIONS.index(a["condition"]) + (a["rep"] - 2) * 0.08, a["speedup"]) for a in rs if a["category"] == k]
            if pts:
                ax.scatter(*zip(*pts), s=42, color=colors[k], edgecolor=muted if k.startswith(("gelijk, geen", "ongewijzigd")) else surface,
                           linewidth=1.0, zorder=3)
        ax.axhline(SPEEDUP_THRESHOLD, color=muted, linestyle="--", linewidth=1)
        ax.axhline(1.0, color=muted, linewidth=0.8)
        if ys and max(ys) > 10:
            ax.set_yscale("log")
            ax.set_ylim(min(min(ys), 0.9) * 0.9, max(max(ys), SPEEDUP_THRESHOLD) * 1.2)
        elif ys:
            ax.set_ylim(min(min(ys), 0.9) - 0.1, max(max(ys), SPEEDUP_THRESHOLD) + 0.15)
        ax.set_title(case, fontsize=10, color=ink)
        ax.set_xticks(range(len(CONDITIONS)), short)
        ax.set_xlim(-0.5, len(CONDITIONS) - 0.5)
        if ax.get_yscale() == "log":
            ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
            ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        ax.spines[["top", "right"]].set_visible(False)
    axes[0].set_ylabel("speedup t.o.v. het origineel (1 = gelijk)")
    fig.suptitle("Snelheidswinst per gelijkwaardig antwoord (stippellijn = drempel 1,2; grijze band = ruis A/A-controle)",
                 x=0.01, ha="left", fontsize=11)
    fig.legend(handles=[h for h in legend if h.get_label() != "fout"], loc="lower center", ncol=4, frameon=False, fontsize=9)
    fig.tight_layout(rect=(0, 0.08, 1, 0.94))
    fig.savefig(outdir / "speedup.png", dpi=200)
    plt.close(fig)
    return True


def main():
    """
    Run the analysis and write the report, the tables, the examples and the figures to ``results/analyse/``.

    Command-line argument: ``--map`` (optional) with the result folders to analyse; without it all full
    runs under ``results/`` are used.

    Returns
    -------
    None
    """
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", nargs="*", help="result folders (default: all full runs under results/)")
    args = ap.parse_args()
    results = ROOT / "results"
    full, mock = pick_folders(results, args.map)
    if not full:
        raise SystemExit("Geen volledige runs gevonden (verwacht: map met llm-results.csv, echt model, vier condities).")
    attempts = load_attempts(full)
    mock_sp = [float(r["speedup"]) for d in mock for r in csv.DictReader(open(d / "llm-results.csv", encoding="utf-8")) if r.get("speedup")]
    report, cond_rows, cc_rows = summarize(attempts, mock_sp)
    out = results / "analyse"
    out.mkdir(exist_ok=True)
    (out / "analyse.txt").write_text(report, encoding="utf-8")
    write_csv(out / "per_poging.csv", attempts, skip=("sql", "explanation"))
    write_csv(out / "per_conditie.csv", cond_rows)
    write_csv(out / "per_casus_conditie.csv", cc_rows)
    write_examples(attempts, out / "voorbeelden.md")
    figs = plot(attempts, mock_sp, out)
    print(report)
    print("\nopgeslagen in", out, "" if figs else "(geen figuren: matplotlib niet geinstalleerd)")


if __name__ == "__main__":
    main()
