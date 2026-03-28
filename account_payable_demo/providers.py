"""LLM provider abstraction and selection for the Account Payable Demo."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from account_payable_demo.config import DemoConfig


class ProviderType(str, Enum):
    """Supported LLM provider types."""

    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    DEEPINFRA = "deepinfra"


class Role(str, Enum):
    """Agent roles in the demo workflow."""

    PLANNER = "planner"
    EXECUTOR = "executor"


@dataclass
class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    model: str
    base_url: Optional[str] = None
    api_key: Optional[str] = None

    @property
    @abstractmethod
    def provider_type(self) -> ProviderType:
        """Return the provider type."""
        pass

    @abstractmethod
    def get_client_config(self) -> dict[str, Any]:
        """
        Get configuration dict for initializing an LLM client.

        Returns a dict with keys appropriate for the provider SDK.
        """
        pass

    @property
    def is_local(self) -> bool:
        """Check if this is a local provider (Ollama)."""
        return self.provider_type == ProviderType.OLLAMA

    @property
    def is_cloud(self) -> bool:
        """Check if this is a cloud provider."""
        return not self.is_local


@dataclass
class OllamaProvider(LLMProvider):
    """Ollama local LLM provider."""

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.OLLAMA

    def get_client_config(self) -> dict[str, Any]:
        """Get Ollama client configuration."""
        return {
            "provider": "ollama",
            "model": self.model,
            "base_url": self.base_url or "http://localhost:11434",
        }


@dataclass
class OpenAIProvider(LLMProvider):
    """OpenAI cloud LLM provider."""

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.OPENAI

    def get_client_config(self) -> dict[str, Any]:
        """Get OpenAI client configuration."""
        config: dict[str, Any] = {
            "provider": "openai",
            "model": self.model,
        }
        if self.api_key:
            config["api_key"] = self.api_key
        if self.base_url:
            config["base_url"] = self.base_url
        return config


@dataclass
class AnthropicProvider(LLMProvider):
    """Anthropic cloud LLM provider."""

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.ANTHROPIC

    def get_client_config(self) -> dict[str, Any]:
        """Get Anthropic client configuration."""
        config: dict[str, Any] = {
            "provider": "anthropic",
            "model": self.model,
        }
        if self.api_key:
            config["api_key"] = self.api_key
        if self.base_url:
            config["base_url"] = self.base_url
        return config


@dataclass
class DeepInfraProvider(LLMProvider):
    """DeepInfra cloud LLM provider."""

    base_url: Optional[str] = field(default="https://api.deepinfra.com/v1/openai")

    @property
    def provider_type(self) -> ProviderType:
        return ProviderType.DEEPINFRA

    def get_client_config(self) -> dict[str, Any]:
        """Get DeepInfra client configuration (OpenAI-compatible)."""
        config: dict[str, Any] = {
            "provider": "deepinfra",
            "model": self.model,
            "base_url": self.base_url,
        }
        if self.api_key:
            config["api_key"] = self.api_key
        return config


def create_provider(
    provider_type: str | ProviderType,
    model: str,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
) -> LLMProvider:
    """
    Create an LLM provider instance.

    Args:
        provider_type: The provider type (ollama, openai, anthropic, deepinfra).
        model: The model name/identifier.
        base_url: Optional base URL override.
        api_key: Optional API key (required for cloud providers).

    Returns:
        An LLMProvider instance.

    Raises:
        ValueError: If the provider type is not supported.
    """
    if isinstance(provider_type, str):
        provider_type = ProviderType(provider_type.lower())

    provider_classes = {
        ProviderType.OLLAMA: OllamaProvider,
        ProviderType.OPENAI: OpenAIProvider,
        ProviderType.ANTHROPIC: AnthropicProvider,
        ProviderType.DEEPINFRA: DeepInfraProvider,
    }

    provider_class = provider_classes.get(provider_type)
    if provider_class is None:
        raise ValueError(f"Unsupported provider type: {provider_type}")

    return provider_class(
        model=model,
        base_url=base_url,
        api_key=api_key,
    )


def get_provider_for_role(config: DemoConfig, role: str | Role) -> LLMProvider:
    """
    Get the appropriate LLM provider for a given role based on config.

    Args:
        config: The demo configuration.
        role: The role (planner or executor).

    Returns:
        An LLMProvider configured for the specified role.

    Raises:
        ValueError: If the role is not recognized.
    """
    if isinstance(role, str):
        role = Role(role.lower())

    if role == Role.PLANNER:
        provider_name = config.get_planner_provider()
        model = config.get_planner_model()
    elif role == Role.EXECUTOR:
        provider_name = config.get_executor_provider()
        model = config.get_executor_model()
    else:
        raise ValueError(f"Unknown role: {role}")

    # Get base URL and API key based on provider
    base_url: Optional[str] = None
    api_key: Optional[str] = None

    if provider_name == "ollama":
        base_url = config.ollama.base_url
    else:
        api_key = config.cloud_llm.get_api_key(provider_name)

    return create_provider(
        provider_type=provider_name,
        model=model,
        base_url=base_url,
        api_key=api_key,
    )


def validate_provider_config(config: DemoConfig) -> list[str]:
    """
    Validate that the provider configuration is complete.

    Args:
        config: The demo configuration.

    Returns:
        A list of validation error messages (empty if valid).
    """
    errors: list[str] = []

    if config.is_cloud_llm:
        # Check planner provider
        planner_provider = config.cloud_llm.planner_provider
        planner_key = config.cloud_llm.get_api_key(planner_provider)
        if planner_provider != "ollama" and not planner_key:
            errors.append(
                f"Missing API key for planner provider '{planner_provider}'. "
                f"Set {planner_provider.upper()}_API_KEY environment variable."
            )

        # Check executor provider
        executor_provider = config.cloud_llm.executor_provider
        executor_key = config.cloud_llm.get_api_key(executor_provider)
        if executor_provider != "ollama" and not executor_key:
            # Only add if different from planner provider (avoid duplicate errors)
            if executor_provider != planner_provider:
                errors.append(
                    f"Missing API key for executor provider '{executor_provider}'. "
                    f"Set {executor_provider.upper()}_API_KEY environment variable."
                )

    return errors
