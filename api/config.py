"""Local-only configuration. Credentials never enter browser contracts."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv
from validator.evaluation import MAX_CORRECTNESS_CHECKS
from validator.timing import MAX_REPETITIONS

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env", override=False)
CONDITIONS = ("C1_query", "C2_schema", "C3_plan", "C4_stats")
LIVE_PROFILE_ORDERS = 512
SQL_RUN_MODES = frozenset({"validate", "live", "live_mock"})
DASHBOARD_CORRECTNESS_TIMEOUT_MS = 10 * 60 * 1_000
DASHBOARD_BENCHMARK_TIMEOUTS_MS = {"top_products": DASHBOARD_CORRECTNESS_TIMEOUT_MS}
# One original and proposal per correctness check and benchmark pair, plus setup time.
SQL_RUN_JOB_TIMEOUT_SECONDS = (MAX_CORRECTNESS_CHECKS + MAX_REPETITIONS) * 2 * (
    DASHBOARD_CORRECTNESS_TIMEOUT_MS // 1_000
) + 300


@dataclass(frozen=True)
class Settings:
    root: Path = ROOT
    data_dir: Path = field(
        default_factory=lambda: Path(os.getenv("SUE_DATA_DIR", str(ROOT / ".local")))
    )
    enable_sql: bool = field(
        default_factory=lambda: os.getenv("SUE_ENABLE_SQL_RUNS") == "1"
    )
    test_database_confirmed: bool = field(
        default_factory=lambda: os.getenv("SUE_TEST_DATABASE_CONFIRMED") == "1"
    )
    enable_llm: bool = field(default_factory=lambda: os.getenv("SUE_ENABLE_LLM") == "1")
    timeout_seconds: int = 300
    allowed_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )

    @property
    def results_dir(self) -> Path:
        return self.root / "results"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "dashboard.sqlite3"
