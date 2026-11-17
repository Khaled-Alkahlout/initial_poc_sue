"""Generation preferences and an explicit small, billable visibility test."""

import time
from llm.analysis import (
    AnalysisError,
    _model_info,
    chat,
    configuration,
    configured_models,
    model_configuration,
)
from llm.generation import (
    GenerationSettings,
    capabilities,
    environment_defaults,
    validate_capabilities,
)


def model_capabilities(requested=None):
    provider, model, _ = model_configuration(GenerationSettings(model=requested))
    if provider != "openrouter":
        raise AnalysisError(
            "Deze Settings-interface ondersteunt OpenRouter; gebruik de legacy-CLI voor directe Anthropic."
        )
    info = _model_info(model, int(time.time() // 60))
    if "response_format" not in info.get("supported_parameters", []):
        raise AnalysisError(
            "Dit OpenRouter-model ondersteunt geen gestructureerde SQL-analyse."
        )
    return info


def settings_view(store, settings, requested=None):
    provider, default_model, key = configuration()
    value = store.generation_settings()
    models = configured_models(provider, default_model)
    if requested is not None and requested not in models:
        raise ValueError("Kies een model uit de serverlijst.")
    model = requested if requested is not None else value.model
    caps, error = None, None
    try:
        caps = capabilities(model_capabilities(model))
    except AnalysisError as exc:
        error = str(exc)
    return {
        "provider": provider,
        "model": model or default_model,
        "models": models,
        "default_model": default_model,
        "key_configured": bool(key),
        "llm_enabled": settings.enable_llm,
        "settings": value.model_dump(),
        "defaults": environment_defaults().model_dump(),
        "capabilities": caps,
        "capabilities_error": error,
        "precedence": "Opgeslagen instellingen > .env-defaults > 4096 tokens / low. Geldt voor volgende aanvragen; bestaande runs behouden hun snapshot.",
        "sql_enabled": settings.enable_sql,
        "test_database_confirmed": settings.test_database_confirmed,
    }


def save_settings(store, value):
    validate_capabilities(value, model_capabilities(value.model))
    store.save_generation_settings(value)


def test_generation(settings, generation=None):
    if not settings.enable_llm:
        raise AnalysisError("Generatie uitgeschakeld: SUE_ENABLE_LLM=1 vereist.")
    _, model, _ = model_configuration(generation)
    caps = capabilities(model_capabilities(generation.model if generation else None))
    effort = next(
        effort
        for effort in ("disabled", "low", "provider")
        if effort in caps["reasoning_efforts"]
    )
    options = GenerationSettings(
        model=model, max_output_tokens=512, reasoning_effort=effort
    )
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
