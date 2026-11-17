"""Prijzen per miljoen tokens (dollar) van de vier Claude-modellen in het modelvergelijkingsexperiment.

Bron: de prijspagina van Claude Platform Docs, opgehaald op 4 november 2026 (platform.claude.com/docs/en/about-claude/pricing).
Haiku 5.5: het lage tarief geldt voor prompts tot 100.000 tokens, ruim boven wat dit experiment verstuurt.
Controleer de prijzen opnieuw voordat je ze in een verslag zet; ze kunnen veranderen.
"""
from __future__ import annotations

# (invoer, uitvoer) in dollar per miljoen tokens
PRICES = {
    "haiku": (0.10, 0.50),
    "sonnet": (2.0, 10.0),
    "opus": (4.0, 20.0),
    "fable": (10.0, 50.0),
}
LABELS = {"haiku": "Haiku 5.5", "sonnet": "Sonnet 5.5", "opus": "Opus 5.5", "fable": "Fable 5.1"}
ORDER = ["haiku", "sonnet", "opus", "fable"]


def family(model: str) -> str:
    """
    Map a model name (Anthropic id or OpenRouter slug) to its family key.

    Parameters
    ----------
    model : str
        Model name, e.g. "claude-sonnet-5-5" or "anthropic/claude-sonnet-5.5".

    Returns
    -------
    str
        One of "haiku", "sonnet", "opus", "fable", or the model name itself when it is not recognised.
    """
    m = model.lower()
    for key in ORDER:
        if key in m:
            return key
    return model


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    """
    Compute the cost of one call from the token counts.

    Parameters
    ----------
    model : str
        Model name, see ``family``.
    input_tokens : int
        Number of input tokens.
    output_tokens : int
        Number of output tokens (including thinking tokens, which are billed as output).

    Returns
    -------
    float or None
        Cost in dollars, or None when the model is not in the price table.
    """
    fam = family(model)
    if fam not in PRICES:
        return None
    pin, pout = PRICES[fam]
    return (input_tokens * pin + output_tokens * pout) / 1e6
