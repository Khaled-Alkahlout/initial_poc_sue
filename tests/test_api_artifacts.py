"""Evidence adapters must never turn ambiguous or missing evidence green."""

import json
import tempfile
import unittest
from pathlib import Path

from api.services.artifacts import Artifacts, adapt_attempt
from api.services.privacy import redact, safe_json


def row(**changes):
    return {
        "case": "top_products",
        "candidate": "candidate",
        "verdict": "ACCEPTED",
        "param_sets": 8,
        "failing_param_sets": 0,
        "orig_median_ms": 100,
        "cand_median_ms": 20,
        "speedup": 5,
        "reps": 7,
        "detail": "",
        **changes,
    }


class ResultAdapterTests(unittest.TestCase):
    def test_accepted_is_only_within_recorded_conditions(self):
        attempt = adapt_attempt(row(), "run", 0)
        self.assertEqual(attempt.outcome, "accepted")
        self.assertEqual(attempt.correctness, "passed")
        self.assertEqual(attempt.benchmark.reduction_percent, 80)
        self.assertIsNone(attempt.stages[4].duration_ms)

    def test_ambiguous_tie_is_not_a_verified_success(self):
        attempt = adapt_attempt(row(detail="big/full: TIE_AMBIGUOUS"), "run", 0)
        self.assertEqual(attempt.outcome, "inconclusive")
        self.assertEqual(attempt.correctness, "inconclusive")
        self.assertIsNone(attempt.benchmark.reduction_percent)
        self.assertEqual(attempt.raw_verdict, "ACCEPTED")

    def test_execution_error_is_not_a_demonstrated_mismatch(self):
        attempt = adapt_attempt(
            row(
                verdict="REJECTED_NOT_EQUIVALENT",
                detail="big/full: EXEC_ERROR QueryCanceled",
            ),
            "run",
            0,
        )
        self.assertEqual(attempt.outcome, "error")
        self.assertEqual(attempt.correctness, "error")

    def test_confirmed_difference_and_missing_details_remain_distinct(self):
        mismatch = adapt_attempt(
            row(verdict="REJECTED_NOT_EQUIVALENT", detail="big/full: VALUE_MISMATCH"),
            "run",
            0,
        )
        unknown = adapt_attempt(row(verdict="REJECTED_NOT_EQUIVALENT"), "run", 0)
        self.assertEqual(mismatch.outcome, "mismatch")
        self.assertEqual(unknown.outcome, "inconclusive")

    def test_empty_parameter_sets_cannot_verify_correctness(self):
        self.assertEqual(
            adapt_attempt(row(param_sets=0), "run", 0).outcome, "inconclusive"
        )

    def test_missing_benchmark_cannot_establish_an_improvement(self):
        attempt = adapt_attempt(row(orig_median_ms=None, cand_median_ms=None), "run", 0)
        self.assertEqual(attempt.outcome, "inconclusive")
        self.assertEqual(attempt.benchmark.status, "skipped")

    def test_static_rejection_skips_correctness(self):
        attempt = adapt_attempt(
            row(verdict="REJECTED_STATIC", param_sets=None), "run", 0
        )
        self.assertEqual(attempt.outcome, "safety_rejected")
        self.assertEqual(attempt.correctness, "skipped")

    def test_missing_and_malformed_artifacts_do_not_crash_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            folder = root / "llm-20261027-220802"
            folder.mkdir()
            (folder / "llm-results.json").write_text("{invalid", encoding="utf-8")
            artifacts = Artifacts(root)
            self.assertEqual(artifacts.runs, {})
            self.assertTrue(artifacts.warnings)
            (folder / "llm-results.json").write_text(
                json.dumps([row(condition="C1_query", rep=1)]), encoding="utf-8"
            )
            artifacts = Artifacts(root)
            attempt = next(iter(artifacts.runs.values())).attempts[0]
            self.assertIsNone(attempt.proposed_sql)
            self.assertEqual(attempt.stages[2].status, "inconclusive")

    def test_artifact_reads_cannot_escape_the_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "results"
            root.mkdir()
            outside = root.parent / "secret.json"
            outside.write_text('{"secret":"private"}')
            self.assertIsNone(Artifacts(root).read(outside))

    def test_malformed_field_types_and_metadata_secrets_are_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory) / "llm-20261027-220802"
            folder.mkdir()
            (folder / "llm-results.json").write_text(
                json.dumps([{"case": ["not-a-string"]}])
            )
            artifacts = Artifacts(Path(directory))
            self.assertTrue(artifacts.warnings)
        attempt = adapt_attempt(
            row(model="sk-ant-never-display", candidate=None, detail=None), "run", 0
        )
        self.assertNotIn("sk-ant-never-display", attempt.model_dump_json())
        self.assertEqual(attempt.candidate, "onbekend")

    def test_context_only_artifact_never_becomes_a_successful_model_run(self):
        from llm.client import build_prompt
        from api.services.artifacts import CASE_MAP

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompts = root / "llm-20261027-203631" / "prompts"
            prompts.mkdir(parents=True)
            (prompts / "top_products__C1_query.txt").write_text(
                build_prompt({"query": CASE_MAP["top_products"].original}),
                encoding="utf-8",
            )
            run = next(iter(Artifacts(root).runs.values()))
            self.assertEqual(run.model_requests, 0)
            self.assertEqual(run.accepted_count, 0)
            self.assertEqual(run.attempts[0].outcome, "unavailable")
            self.assertEqual(run.attempts[0].correctness, "skipped")
            self.assertTrue(
                all(
                    s.status == "skipped"
                    for s in run.attempts[0].stages
                    if s.id in {"generation", "correctness", "benchmark"}
                )
            )

    def test_empty_artifact_catalog_keeps_missing_model_metrics_unknown(self):
        from api.config import Settings
        from api.services.catalog import Catalog
        from api.services.storage import Store

        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(
                root=Path(directory), data_dir=Path(directory) / "state"
            )
            overview = Catalog(settings, Store(settings.database_path)).overview()
            self.assertIsNone(
                next(m.value for m in overview.metrics if m.id == "requests")
            )
            self.assertIsNone(
                next(m.value for m in overview.metrics if m.id == "accepted")
            )

    def test_redaction_covers_secrets_and_context_values(self):
        secret = "postgresql://user:very-private@localhost/db sk-ant-private-secret a@example.com 00000000-0000-0000-0000-000000000001 mcv={customer-name}"
        safe = redact(secret, literals=True)
        for value in (
            "very-private",
            "sk-ant-private-secret",
            "a@example.com",
            "00000000-0000",
            "customer-name",
        ):
            self.assertNotIn(value, safe)
        self.assertEqual(safe_json({"password": "hidden"})["password"], "[geredigeerd]")
        self.assertIn(
            "'paid'", redact("SELECT 'paid', 'customer-private'", literals=True)
        )
        self.assertNotIn(
            "customer-private",
            redact("SELECT 'paid', 'customer-private'", literals=True),
        )


if __name__ == "__main__":
    unittest.main()
