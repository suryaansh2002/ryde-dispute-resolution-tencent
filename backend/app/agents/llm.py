"""Per-call model settings shared by every agent, built from `app.config.settings`."""

from typing import Any

from pydantic_ai import NativeOutput, PromptedOutput
from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModelSettings
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openrouter import OpenRouterModelSettings
from pydantic_ai.settings import ModelSettings

from app.config import settings


def _fallbacks(fallback_models: str) -> list[str]:
    return [m.strip() for m in fallback_models.split(",") if m.strip()]


def _model(model: str, fallback_models: str) -> Model | str:
    """OpenRouter does its own fallback (see `_model_settings`); any other provider gets
    pydantic-ai's FallbackModel, which moves to the next model on an API error. Its
    fallbacks are full "<provider>:<model>" strings, e.g. "google:gemini-3.5-flash-lite"."""
    fallbacks = _fallbacks(fallback_models)
    if model.startswith("openrouter:") or not fallbacks:
        return model
    return FallbackModel(model, *fallbacks)


def _model_settings(model: str, fallback_models: str) -> ModelSettings:
    model_settings: ModelSettings
    if model.startswith("anthropic:"):
        model_settings = AnthropicModelSettings(max_tokens=settings.agent_max_tokens)
        if settings.agent_effort:
            model_settings["anthropic_effort"] = settings.agent_effort
    elif model.startswith("openrouter:"):
        model_settings = OpenRouterModelSettings(max_tokens=settings.agent_max_tokens)
        fallbacks = _fallbacks(fallback_models)
        if fallbacks:
            model_settings["openrouter_models"] = fallbacks
    else:
        model_settings = ModelSettings(max_tokens=settings.agent_max_tokens)
    if settings.agent_temperature is not None:
        model_settings["temperature"] = settings.agent_temperature
    return model_settings


def output_spec(output_type: type) -> Any:
    """`output_type` wrapped per AGENT_OUTPUT_MODE; validators see the same typed object."""
    if settings.agent_output_mode == "native":
        return NativeOutput(output_type)
    if settings.agent_output_mode == "prompted":
        return PromptedOutput(output_type)
    return output_type


def agent_model() -> Model | str:
    return _model(settings.agent_model, settings.agent_fallback_models)


def vision_model() -> Model | str:
    return _model(settings.vision_model, settings.vision_fallback_models)


def agent_model_settings() -> ModelSettings:
    return _model_settings(settings.agent_model, settings.agent_fallback_models)


def vision_model_settings() -> ModelSettings:
    return _model_settings(settings.vision_model, settings.vision_fallback_models)
