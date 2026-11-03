"""Generation preferences and an explicit small, billable visibility test."""

import time
from llm.analysis import AnalysisError, _model_info, chat, configuration
from llm.generation import (
    GenerationSettings,
    capabilities,
    environment_defaults,
    validate_capabilities,
)


def model_capabilities():
    provider, model, _ = configuration()
    if provider != "openrouter":
        raise AnalysisError(
            "Deze Settings-interface ondersteunt OpenRouter; gebruik de legacy-CLI voor directe Anthropic."
        )
    return _model_info(model, int(time.time() // 60))


def settings_view(store, settings):
    provider, model, key = configuration()
    caps, error = None, None
    try:
        caps = capabilities(model_capabilities())
    except AnalysisError as exc:
        error = str(exc)
    return {
        "provider": provider,
        "model": model,
        "key_configured": bool(key),
        "llm_enabled": settings.enable_llm,
        "settings": store.generation_settings().model_dump(),
        "defaults": environment_defaults().model_dump(),
        "capabilities": caps,
        "capabilities_error": error,
        "precedence": "Opgeslagen instellingen > .env-defaults > 4096 tokens / low. Geldt voor volgende aanvragen; bestaande runs behouden hun snapshot.",
        "sql_enabled": settings.enable_sql,
        "test_database_confirmed": settings.test_database_confirmed,
    }


def save_settings(store, value):
    validate_capabilities(value, model_capabilities())
    store.save_generation_settings(value)


def test_generation(settings):
    if not settings.enable_llm:
        raise AnalysisError("Generatie uitgeschakeld: SUE_ENABLE_LLM=1 vereist.")
    _, model, _ = configuration()
    caps = capabilities(model_capabilities())
    effort = "disabled" if "disabled" in caps["reasoning_efforts"] else "low"
    options = GenerationSettings(max_output_tokens=512, reasoning_effort=effort)
    try:
        result = chat(
            [
                {
                    "role": "system",
                    "content": "Antwoord uitsluitend met OK. Gebruik geen uitleg.",
                },
                {"role": "user", "content": "Verbindingstest: antwoord OK."},
            ],
            model,
            generation=options,
        )
        success = result["text"].strip() == "OK"
        return {
            "success": success,
            "message": "Zichtbare modeloutput OK ontvangen."
            if success
            else "Inhoud ontvangen, maar niet het verwachte OK-antwoord.",
            "diagnostics": result["diagnostics"],
            "test_settings": options.model_dump(),
        }
    except AnalysisError as exc:
        return {
            "success": False,
            "message": str(exc),
            "diagnostics": exc.diagnostics,
            "test_settings": options.model_dump(),
        }
