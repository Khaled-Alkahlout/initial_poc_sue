"""Conservative display redaction; it never edits source artifacts."""

import re
from typing import Any

PUBLIC_LITERALS = {
    "paid",
    "processing",
    "shipped",
    "delivered",
    "delivery",
    "orders",
    "customers",
}
SENSITIVE_KEYS = {
    "password",
    "api_key",
    "secret",
    "database_url",
    "connection_uri",
    "authorization",
}


def redact(text: str, *, literals: bool = False) -> str:
    text = re.sub(
        r"(?:postgres(?:ql)?(?:\+\w+)?|https?)://[^\s\"<>]+",
        "[URI geredigeerd]",
        text,
        flags=re.I,
    )
    text = re.sub(r"\b(?:sk-ant-|sk-)[A-Za-z0-9_-]+", "[sleutel geredigeerd]", text)
    text = re.sub(
        r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
        "[e-mail geredigeerd]",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b",
        "[UUID geredigeerd]",
        text,
        flags=re.I,
    )
    text = re.sub(
        r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:[+-]\d{2}:?\d{2})?)?\b",
        "[datum geredigeerd]",
        text,
    )
    text = re.sub(r"mcv=.*", "mcv=[waarden geredigeerd]", text)
    text = re.sub(
        r"(?i)(password|api_key|secret|authorization)\s*[:=]\s*[^\s,;]+",
        r"\1=[geredigeerd]",
        text,
    )
    if literals:
        text = re.sub(
            r"'((?:[^']|'')*)'",
            lambda m: m.group(0)
            if m.group(1) in PUBLIC_LITERALS
            else "'[geredigeerd]'",
            text,
        )
    return text


def safe_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(k): "[geredigeerd]"
            if str(k).lower() in SENSITIVE_KEYS
            else safe_json(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [safe_json(v) for v in value]
    if isinstance(value, str):
        return redact(value, literals=True)
    if isinstance(value, float):
        import math

        return value if math.isfinite(value) else None
    return value
