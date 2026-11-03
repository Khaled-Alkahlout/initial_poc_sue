"""Validated generation options. Secrets and SQL execution flags never belong here."""

import os
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

TOKEN_PRESETS = (512, 1024, 2048, 4096, 8192, 16384)


class GenerationSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    max_output_tokens: int | None = 4096
    reasoning_effort: Literal["disabled", "low", "medium", "high"] = "low"
    temperature: float | None = Field(default=None, ge=0, le=2, allow_inf_nan=False)

    @field_validator("max_output_tokens")
    @classmethod
    def token_budget(cls, value):
        if value is not None and value not in TOKEN_PRESETS:
            raise ValueError(
                "Kies een ondersteund tokenpreset of null voor provider-default."
            )
        return value


def environment_defaults() -> GenerationSettings:
    raw = os.getenv("SUE_MAX_OUTPUT_TOKENS", "4096").strip().lower()
    return GenerationSettings(
        max_output_tokens=None if raw == "provider" else int(raw),
        reasoning_effort=os.getenv("SUE_REASONING_EFFORT", "low"),
    )


def capabilities(info: dict) -> dict:
    parameters = info.get("supported_parameters", [])
    reasoning = info.get("reasoning") or {}
    efforts = reasoning.get("supported_efforts", [])
    # A null list explicitly accepts all gateway levels; absence is unknown.
    supported = (
        ["low", "medium", "high"]
        if efforts is None
        else [e for e in ("low", "medium", "high") if e in efforts]
    )
    if not reasoning.get("mandatory", False) and (efforts is None or "none" in efforts):
        supported.insert(0, "disabled")
    if "reasoning" not in parameters:
        supported = []
    return {
        "reasoning_efforts": supported,
        "temperature_supported": "temperature" in parameters,
        "max_output_tokens": (info.get("top_provider") or {}).get(
            "max_completion_tokens"
        ),
        "provider_default_supported": True,
        "max_tokens_supported": "max_tokens" in parameters,
    }


def validate_capabilities(settings: GenerationSettings, info: dict) -> dict:
    caps = capabilities(info)
    if settings.reasoning_effort not in caps["reasoning_efforts"]:
        raise ValueError(
            "Het ingestelde model ondersteunt deze reasoning-effort niet; instelling wordt niet genegeerd."
        )
    if settings.temperature is not None and not caps["temperature_supported"]:
        raise ValueError(
            "Temperature wordt niet ondersteund door het ingestelde model. Kies provider-default (null)."
        )
    if settings.max_output_tokens is not None:
        if not caps["max_tokens_supported"]:
            raise ValueError("Het ingestelde model ondersteunt max_tokens niet.")
        if (
            caps["max_output_tokens"] is not None
            and settings.max_output_tokens > caps["max_output_tokens"]
        ):
            raise ValueError("Outputbudget overschrijdt de gerapporteerde modellimiet.")
    return caps
