"""Local-only configuration. Credentials never enter browser contracts."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONDITIONS = ("C1_query", "C2_schema", "C3_plan", "C4_stats")


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
