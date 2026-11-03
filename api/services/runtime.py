"""Prevent a long-lived API and freshly spawned workers from mixing code versions."""

import hashlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def source_revision():
    digest = hashlib.sha256()
    for folder in ("api", "llm"):
        for path in sorted((PROJECT_ROOT / folder).rglob("*.py")):
            digest.update(path.relative_to(PROJECT_ROOT).as_posix().encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


LOADED_REVISION = source_revision()


class RuntimeMismatch(Exception):
    pass


def ensure_current(expected=None):
    if source_revision() != LOADED_REVISION or (
        expected is not None and expected != LOADED_REVISION
    ):
        raise RuntimeMismatch(
            "Backendcode is gewijzigd. Herstart de Python-API voordat je verdergaat; er is geen nieuwe taak gestart."
        )
