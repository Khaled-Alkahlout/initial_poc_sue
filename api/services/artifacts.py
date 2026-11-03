"""Read-only adapters for legacy artifacts; no validator algorithms are changed."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime
from pathlib import Path

from api.config import CONDITIONS
from api.schemas import Attempt, Benchmark, ContextSection, RunDetail, Stage, TestRecord
from api.services.privacy import redact, safe_json
from cases.cases import CASES
from llm.client import HEADERS

CASE_MAP = {case.name: case for case in CASES}
LIMITATIONS = [
    "Correctheid geldt alleen voor geteste data en parameters; geen algemeen bewijs van SQL-equivalentie.",
    "De legacy-validator kan ties te ruim toestaan en resultaatwaarden gelijk normaliseren. Ambigue resultaten worden hier niet als succes getoond.",
    "Benchmarktijden zijn metingen op een testdataset; mockworkloadcijfers beschrijven geen gemeten databasebelasting.",
    "Geen productiegoedkeuring, automatisch indexbeheer of tweede controle-agent.",
]
STAGE_LABELS = {
    "selection": "Queryselectie",
    "context": "Context voorbereiden",
    "generation": "LLM-generatie",
    "static": "Statische SQL-controle",
    "correctness": "Correctheid",
    "benchmark": "Performancebenchmark",
    "result": "Eindresultaat",
}


def stage(
    key: str, status: str, note: str, origin="historical", duration_ms=None
) -> Stage:
    return Stage(
        id=key,
        label=STAGE_LABELS[key],
        status=status,
        note=note,
        origin=origin,
        duration_ms=duration_ms,
    )


def number(row: dict, key: str) -> float | None:
    value = row.get(key)
    return (
        float(value)
        if type(value) in (float, int) and math.isfinite(value) and value >= 0
        else None
    )


def integer(row: dict, key: str) -> int | None:
    value = row.get(key)
    return value if type(value) is int and value >= 0 else None


def context_sections(prompt: str | None, condition: str | None) -> list[ContextSection]:
    sections = {}
    if prompt:
        for title, body in re.findall(
            r"^## (.*?)\r?\n```[^\n]*\n(.*?)```", prompt, re.M | re.S
        ):
            sections[title.strip()] = body.rstrip()
    level = CONDITIONS.index(condition) if condition in CONDITIONS else -1
    result = []
    for index, (key, label) in enumerate(HEADERS.items()):
        body = sections.get(label)
        if body is None:
            omitted = level >= 0 and index > level
            result.append(
                ContextSection(
                    id=key,
                    label=label,
                    state="omitted" if omitted else "unavailable",
                    note="Niet opgenomen in deze conditie."
                    if omitted
                    else "Niet beschikbaar in het artefact.",
                )
            )
            continue
        safe = redact(body, literals=True)
        truncated = "(afgekapt)" in body or len(safe) > 16000
        result.append(
            ContextSection(
                id=key,
                label=label,
                state="truncated"
                if truncated
                else "redacted"
                if safe != body
                else "available",
                text=safe[:16000],
                note="Literals en gevoelige waarden worden beperkt; bronbestand blijft ongewijzigd.",
            )
        )
    return result


def adapt_attempt(
    row: dict,
    run_id: str,
    index: int,
    response: dict | None = None,
    prompt: str | None = None,
    origin="historical",
    handwritten=False,
) -> Attempt:
    """Interpret evidence conservatively, retaining the original verdict separately."""
    query_id = row["case"] if isinstance(row.get("case"), str) else "onbekend"
    candidate = (
        redact(row["candidate"])
        if isinstance(row.get("candidate"), str)
        else "onbekend"
    )
    detail = row["detail"] if isinstance(row.get("detail"), str) else ""
    condition = row.get("condition") if row.get("condition") in CONDITIONS else None
    verdict = row.get("verdict") if isinstance(row.get("verdict"), str) else None
    sets, failing = integer(row, "param_sets"), integer(row, "failing_param_sets")
    if verdict == "REJECTED_STATIC":
        outcome, correctness = "safety_rejected", "skipped"
    elif "EXEC_ERROR" in detail:
        outcome, correctness = "error", "error"
    elif any(
        code in detail
        for code in (
            "VALUE_MISMATCH",
            "ROWCOUNT_MISMATCH",
            "COLUMN_MISMATCH",
            "ORDER_MISMATCH",
        )
    ):
        outcome, correctness = "mismatch", "failed"
    elif "TIE_AMBIGUOUS" in detail:
        outcome, correctness = "inconclusive", "inconclusive"
    elif verdict in {"ACCEPTED", "EQUIVALENT_NOT_FASTER"} and sets and failing == 0:
        outcome, correctness = (
            ("accepted" if verdict == "ACCEPTED" else "not_faster"),
            "passed",
        )
    else:
        outcome, correctness = "inconclusive", "inconclusive"

    original = CASE_MAP.get(query_id)
    proposed = (
        response.get("sql")
        if response and isinstance(response.get("sql"), str)
        else None
    )
    if handwritten and original:
        proposed = next(
            (c.sql for c in original.candidates if c.name == candidate), None
        )
    original_ms, proposed_ms = (
        number(row, "orig_median_ms"),
        number(row, "cand_median_ms"),
    )
    measured = original_ms is not None and proposed_ms is not None
    if outcome in {"accepted", "not_faster"} and not measured:
        outcome = "inconclusive"
    benchmark_status = (
        ("passed" if outcome == "accepted" else "warning")
        if measured and correctness == "passed"
        else "inconclusive"
        if measured
        else "skipped"
    )
    benchmark = Benchmark(
        original_ms=original_ms,
        proposed_ms=proposed_ms,
        original_iqr_ms=number(row, "orig_iqr_ms"),
        proposed_iqr_ms=number(row, "cand_iqr_ms"),
        speedup=number(row, "speedup"),
        repetitions=integer(row, "reps"),
        reduction_percent=(1 - proposed_ms / original_ms) * 100
        if correctness == "passed" and measured and original_ms > 0
        else None,
        status=benchmark_status,
        origin=origin,
    )
    model = redact(row["model"]) if isinstance(row.get("model"), str) else None
    llm_seconds = number(row, "llm_seconds")
    final_status = {
        "accepted": "passed",
        "not_faster": "warning",
        "mismatch": "failed",
        "safety_rejected": "failed",
        "error": "error",
    }.get(outcome, "inconclusive")
    stages = [
        stage(
            "selection",
            "skipped",
            "Geen selectiesnapshot in dit historische artefact; huidige mockranking is apart beschikbaar.",
            origin,
        ),
        stage(
            "context",
            "passed" if prompt else "skipped",
            "Opgeslagen prompt beschikbaar."
            if prompt
            else "Context niet vastgelegd of niet van toepassing.",
            origin,
        ),
        stage(
            "generation",
            "skipped" if handwritten else "passed" if response else "inconclusive",
            "Handgemaakte kandidaat; geen modelrequest."
            if handwritten
            else "Opgeslagen response; geen nieuwe modelcall."
            if response
            else "Responsartefact ontbreekt.",
            origin,
            llm_seconds * 1000 if llm_seconds is not None else None,
        ),
        stage(
            "static",
            "failed"
            if verdict == "REJECTED_STATIC"
            else "passed"
            if sets
            else "inconclusive",
            "Statische afwijzing vastgelegd."
            if verdict == "REJECTED_STATIC"
            else "Status afgeleid uit de geregistreerde validatorfase; geen nieuwe controle.",
            origin,
        ),
        stage(
            "correctness",
            correctness,
            redact(detail) or "Resultaat gelijk binnen de geregistreerde parametersets."
            if correctness == "passed"
            else redact(detail) or "Onvoldoende bewijs of niet uitgevoerd.",
            origin,
        ),
        stage(
            "benchmark",
            benchmark_status,
            (
                "Geregistreerde medianen en spreiding; geen nieuwe meting."
                if origin == "historical"
                else "Nieuwe meting door de bestaande benchmark; fase-duur niet afzonderlijk vastgelegd."
            )
            if measured
            else "Geen benchmark beschikbaar.",
            origin,
        ),
        stage(
            "result",
            final_status,
            "Oordeel binnen de geteste voorwaarden; legacy-oordeel blijft apart zichtbaar.",
            origin,
        ),
    ]
    unchanged = row.get("unchanged") if type(row.get("unchanged")) is bool else None
    if original and proposed:
        # AST formatting preserves string literal content; this is no equivalence claim.
        try:
            import sqlglot

            unchanged = (
                sqlglot.parse_one(original.original, read="postgres").sql()
                == sqlglot.parse_one(proposed, read="postgres").sql()
            )
        except sqlglot.errors.SqlglotError:
            unchanged = None
    explanation = (
        response.get("text")
        if response and isinstance(response.get("text"), str)
        else None
    )
    return Attempt(
        id=f"{run_id}~{index}",
        run_id=run_id,
        query_id=query_id,
        candidate=candidate,
        condition=condition,
        repetition=integer(row, "rep"),
        model=model,
        raw_verdict=redact(verdict) if verdict else None,
        outcome=outcome,
        correctness=correctness,
        original_sql=original.original if original else None,
        proposed_sql=redact(proposed, literals=True) if proposed else None,
        explanation=redact(explanation, literals=True)[:20000] if explanation else None,
        detail=redact(detail),
        parameter_sets=sets,
        failing_parameter_sets=failing,
        input_tokens=integer(row, "input_tokens"),
        output_tokens=integer(row, "output_tokens"),
        llm_seconds=llm_seconds,
        unchanged=unchanged,
        stages=stages,
        benchmark=benchmark,
        context=context_sections(prompt, condition),
        raw_record=safe_json(row),
        origin=origin,
    )


def summarize(run: RunDetail) -> RunDetail:
    attempts = run.attempts
    run.query_ids = sorted({a.query_id for a in attempts}) or run.query_ids
    run.attempt_count = len(attempts)
    run.accepted_count = sum(a.outcome == "accepted" for a in attempts)
    run.issue_count = sum(
        a.outcome in {"mismatch", "safety_rejected", "error", "inconclusive"}
        for a in attempts
    )
    for field in ("input_tokens", "output_tokens"):
        values = [getattr(a, field) for a in attempts]
        setattr(
            run,
            field,
            sum(values) if values and all(v is not None for v in values) else None,
        )
    run.model_requests = (
        0
        if run.mode in {"replay", "mock", "live_mock"}
        else sum(a.model not in {None, "mock"} for a in attempts)
        if attempts
        else None
    )
    return run


class Artifacts:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.warnings: list[str] = []
        self.runs: dict[str, RunDetail] = {}
        self.tests: dict[str, TestRecord] = {}
        self._load()

    def read(self, path: Path, *, text=False):
        try:
            if (
                not path.resolve().is_relative_to(self.root)
                or path.stat().st_size > 2_000_000
            ):
                raise ValueError("ongeldig of te groot artefact")
            content = path.read_text(encoding="utf-8-sig")
            return content[:100000] if text else json.loads(content)
        except (OSError, ValueError, UnicodeError):
            self.warnings.append(f"Artefact niet leesbaar: {path.name}.")
            return None

    @staticmethod
    def timestamp(name: str) -> str:
        match = re.search(r"(\d{8}-\d{6})", name)
        if match:
            try:
                return datetime.strptime(match[1], "%Y%m%d-%H%M%S").isoformat()
            except ValueError:
                pass
        return "onbekend"

    def _load(self):
        for path in sorted(self.root.glob("llm-*/llm-results.json")):
            rows = self.read(path)
            if not isinstance(rows, list):
                self.warnings.append(
                    f"Geen geldige resultatenlijst: {path.parent.name}."
                )
                continue
            run_id = path.parent.name
            attempts = []
            for index, row in enumerate(rows):
                if (
                    not isinstance(row, dict)
                    or not isinstance(row.get("case"), str)
                    or row["case"] not in CASE_MAP
                ):
                    self.warnings.append(f"Onbekend record overgeslagen: {run_id}.")
                    continue
                # Filenames are assembled only from allowlisted case/condition and an integer rep.
                condition, rep = row.get("condition"), integer(row, "rep")
                response, prompt = None, None
                if condition in CONDITIONS and rep is not None:
                    tag = f"{row['case']}__{condition}"
                    response = self.read(
                        path.parent / "responses" / f"{tag}__r{rep}.json"
                    )
                    prompt = self.read(
                        path.parent / "prompts" / f"{tag}.txt", text=True
                    )
                try:
                    attempts.append(
                        adapt_attempt(
                            row,
                            run_id,
                            index,
                            response if isinstance(response, dict) else None,
                            prompt,
                        )
                    )
                except (ValueError, TypeError, OverflowError):
                    self.warnings.append(
                        f"Ongeldig resultaat overgeslagen: {run_id}, record {index}."
                    )
            self.runs[run_id] = summarize(
                RunDetail(
                    id=run_id,
                    title="Historisch experiment",
                    mode="historical",
                    lifecycle="COMPLETED",
                    created_at=self.timestamp(run_id),
                    attempts=attempts,
                    limitations=LIMITATIONS,
                )
            )
        # A dry-run with prompts is an inspectable historical run, not a successful analysis.
        for folder in sorted(self.root.glob("llm-*")):
            if not folder.is_dir() or folder.name in self.runs:
                continue
            attempts = []
            for path in sorted((folder / "prompts").glob("*.txt")):
                query_id, separator, condition = path.stem.partition("__")
                if (
                    not separator
                    or query_id not in CASE_MAP
                    or condition not in CONDITIONS
                ):
                    continue
                prompt = self.read(path, text=True)
                if prompt is None:
                    continue
                attempt = adapt_attempt(
                    {
                        "case": query_id,
                        "candidate": "context_only",
                        "condition": condition,
                    },
                    folder.name,
                    len(attempts),
                    prompt=prompt,
                )
                attempt.outcome, attempt.correctness = "unavailable", "skipped"
                attempt.stages = [
                    stage(
                        "context",
                        "passed",
                        "Userprompt aanwezig; geen response of resultaat vastgelegd.",
                    )
                ] + [
                    stage(
                        key,
                        "skipped",
                        "Alleen context opgeslagen; deze fase is niet vastgelegd.",
                    )
                    for key in (
                        "generation",
                        "static",
                        "correctness",
                        "benchmark",
                        "result",
                    )
                ]
                attempt.stages.insert(
                    0,
                    stage("selection", "skipped", "Geen selectiesnapshot beschikbaar."),
                )
                attempts.append(attempt)
            if attempts:
                self.runs[folder.name] = summarize(
                    RunDetail(
                        id=folder.name,
                        title="Historisch · alleen context",
                        mode="historical",
                        lifecycle="COMPLETED",
                        created_at=self.timestamp(folder.name),
                        attempts=attempts,
                        limitations=LIMITATIONS,
                    )
                )
        for path in sorted(self.root.glob("validation-*.json")):
            rows = self.read(path)
            if not isinstance(rows, list):
                continue
            for index, row in enumerate(rows):
                if (
                    not isinstance(row, dict)
                    or not isinstance(row.get("case"), str)
                    or row["case"] not in CASE_MAP
                ):
                    continue
                try:
                    attempt = adapt_attempt(row, path.stem, index, handwritten=True)
                    expected = (
                        row.get("expected")
                        if row.get("expected") in {"equivalent", "not_equivalent"}
                        else None
                    )
                    if attempt.correctness in {"inconclusive", "error"}:
                        status = attempt.correctness
                    elif expected is None:
                        status = "inconclusive"
                    else:
                        actual_rejection = attempt.outcome in {
                            "mismatch",
                            "safety_rejected",
                        }
                        status = (
                            "passed"
                            if actual_rejection == (expected == "not_equivalent")
                            else "failed"
                        )
                    test_id = f"{path.stem}~{index}"
                    self.tests[test_id] = TestRecord(
                        id=test_id,
                        name=f"{attempt.query_id} / {attempt.candidate}",
                        component="SQL-validator",
                        purpose="Mutatietest: validatoruitkomst vergelijken met het handmatige label van de maker.",
                        expected=expected,
                        actual=attempt.raw_verdict,
                        status=status,
                        executed_at=self.timestamp(path.stem),
                        query_id=attempt.query_id,
                        origin="historical",
                        detail=attempt.detail
                        or (
                            "Validatoruitkomst wijkt af van het auteurslabel. Onderzoek de fixture en de kandidaat; het label is geen onafhankelijk bewijs."
                            if status == "failed"
                            else "Verwachting is een auteurslabel, geen onafhankelijk equivalentiebewijs."
                        ),
                        attempt=attempt,
                        error_classification=(
                            "MISSED_MUTATION"
                            if expected == "not_equivalent"
                            else "FALSE_REJECTION"
                        )
                        if status == "failed"
                        else attempt.outcome
                        if status != "passed"
                        else None,
                        metadata={"artifact": path.name, "fault": row.get("fault")},
                    )
                except (ValueError, TypeError, OverflowError):
                    self.warnings.append(
                        f"Ongeldige evaluatie overgeslagen: {path.name}."
                    )

    def replay(
        self, query_id: str, condition: str, source_id: str | None = None
    ) -> tuple[RunDetail, Attempt] | None:
        for run in sorted(self.runs.values(), key=lambda r: r.created_at, reverse=True):
            if source_id and run.id != source_id:
                continue
            attempt = next(
                (
                    a
                    for a in run.attempts
                    if a.query_id == query_id
                    and a.condition == condition
                    and a.proposed_sql
                ),
                None,
            )
            if attempt:
                return run, attempt
        return None
