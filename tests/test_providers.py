"""Tests for LLM provider selection and abstraction."""

from __future__ import annotations

import pytest

from account_payable_demo.config import (
    CloudLLMConfig,
    DemoConfig,
    LLMMode,
    OllamaConfig,
)
from account_payable_demo.providers import (
    AnthropicProvider,
    DeepInfraProvider,
    OllamaProvider,
    OpenAIProvider,
    ProviderType,
    Role,
    create_provider,
    get_provider_for_role,
    validate_provider_config,
)


class TestProviderType:
    """Tests for ProviderType enum."""

    def test_ollama_value(self):
        assert ProviderType.OLLAMA.value == "ollama"

    def test_openai_value(self):
        assert ProviderType.OPENAI.value == "openai"

    def test_anthropic_value(self):
        assert ProviderType.ANTHROPIC.value == "anthropic"

    def test_deepinfra_value(self):
        assert ProviderType.DEEPINFRA.value == "deepinfra"


class TestRole:
    """Tests for Role enum."""

    def test_planner_value(self):
        assert Role.PLANNER.value == "planner"

    def test_executor_value(self):
        assert Role.EXECUTOR.value == "executor"


class TestOllamaProvider:
    """Tests for OllamaProvider."""

    def test_is_local(self):
        provider = OllamaProvider(model="llama3:8b")
        assert provider.is_local is True
        assert provider.is_cloud is False

    def test_get_client_config(self):
        provider = OllamaProvider(
            model="llama3:8b",
            base_url="http://custom:1234",
        )
        config = provider.get_client_config()

        assert config["provider"] == "ollama"
        assert config["model"] == "llama3:8b"
        assert config["base_url"] == "http://custom:1234"

    def test_get_client_config_default_url(self):
        provider = OllamaProvider(model="llama3:8b")
        config = provider.get_client_config()

        assert config["base_url"] == "http://localhost:11434"


class TestOpenAIProvider:
    """Tests for OpenAIProvider."""

    def test_is_cloud(self):
        provider = OpenAIProvider(model="gpt-4o")
        assert provider.is_cloud is True
        assert provider.is_local is False

    def test_get_client_config(self):
        provider = OpenAIProvider(
            model="gpt-4o",
            api_key="sk-test123",
        )
        config = provider.get_client_config()

        assert config["provider"] == "openai"
        assert config["model"] == "gpt-4o"
        assert config["api_key"] == "sk-test123"

    def test_get_client_config_no_key(self):
        provider = OpenAIProvider(model="gpt-4o")
        config = provider.get_client_config()

        assert config["provider"] == "openai"
        assert config["model"] == "gpt-4o"
        assert "api_key" not in config

    def test_get_client_config_with_base_url(self):
        provider = OpenAIProvider(
            model="gpt-4o",
            base_url="https://custom.openai.azure.com",
        )
        config = provider.get_client_config()

        assert config["base_url"] == "https://custom.openai.azure.com"


class TestAnthropicProvider:
    """Tests for AnthropicProvider."""

    def test_is_cloud(self):
        provider = AnthropicProvider(model="claude-3-opus")
        assert provider.is_cloud is True

    def test_get_client_config(self):
        provider = AnthropicProvider(
            model="claude-3-opus",
            api_key="sk-ant-test",
        )
        config = provider.get_client_config()

        assert config["provider"] == "anthropic"
        assert config["model"] == "claude-3-opus"
        assert config["api_key"] == "sk-ant-test"


class TestDeepInfraProvider:
    """Tests for DeepInfraProvider."""

    def test_default_base_url(self):
        provider = DeepInfraProvider(model="meta-llama/Llama-2-70b-chat-hf")
        assert provider.base_url == "https://api.deepinfra.com/v1/openai"

    def test_get_client_config(self):
        provider = DeepInfraProvider(
            model="meta-llama/Llama-2-70b-chat-hf",
            api_key="di-test",
        )
        config = provider.get_client_config()

        assert config["provider"] == "deepinfra"
        assert config["model"] == "meta-llama/Llama-2-70b-chat-hf"
        assert config["api_key"] == "di-test"
        assert config["base_url"] == "https://api.deepinfra.com/v1/openai"


class TestCreateProvider:
    """Tests for create_provider function."""

    def test_create_ollama(self):
        provider = create_provider(
            provider_type="ollama",
            model="llama3:8b",
            base_url="http://localhost:11434",
        )
        assert isinstance(provider, OllamaProvider)
        assert provider.model == "llama3:8b"

    def test_create_openai(self):
        provider = create_provider(
            provider_type="openai",
            model="gpt-4o",
            api_key="sk-test",
        )
        assert isinstance(provider, OpenAIProvider)
        assert provider.model == "gpt-4o"
        assert provider.api_key == "sk-test"

    def test_create_anthropic(self):
        provider = create_provider(
            provider_type="anthropic",
            model="claude-3-opus",
            api_key="sk-ant-test",
        )
        assert isinstance(provider, AnthropicProvider)
        assert provider.model == "claude-3-opus"

    def test_create_deepinfra(self):
        provider = create_provider(
            provider_type="deepinfra",
            model="meta-llama/Llama-2-70b-chat-hf",
            api_key="di-test",
        )
        assert isinstance(provider, DeepInfraProvider)

    def test_create_with_enum(self):
        provider = create_provider(
            provider_type=ProviderType.OLLAMA,
            model="llama3:8b",
        )
        assert isinstance(provider, OllamaProvider)

    def test_create_unknown_provider(self):
        with pytest.raises(ValueError, match="is not a valid ProviderType"):
            create_provider(
                provider_type="unknown",
                model="test",
            )


class TestGetProviderForRole:
    """Tests for get_provider_for_role function."""

    def test_get_planner_provider_local(self):
        config = DemoConfig(
            llm_mode=LLMMode.LOCAL,
            ollama=OllamaConfig(
                base_url="http://ollama:11434",
                planner_model="llama3:8b",
            ),
        )
        provider = get_provider_for_role(config, Role.PLANNER)

        assert isinstance(provider, OllamaProvider)
        assert provider.model == "llama3:8b"
        assert provider.base_url == "http://ollama:11434"

    def test_get_executor_provider_local(self):
        config = DemoConfig(
            llm_mode=LLMMode.LOCAL,
            ollama=OllamaConfig(
                base_url="http://ollama:11434",
                executor_model="phi3:mini",
            ),
        )
        provider = get_provider_for_role(config, Role.EXECUTOR)

        assert isinstance(provider, OllamaProvider)
        assert provider.model == "phi3:mini"

    def test_get_planner_provider_cloud(self):
        config = DemoConfig(
            llm_mode=LLMMode.CLOUD,
            cloud_llm=CloudLLMConfig(
                planner_provider="openai",
                planner_model="gpt-4o",
                openai_api_key="sk-test",
            ),
        )
        provider = get_provider_for_role(config, "planner")

        assert isinstance(provider, OpenAIProvider)
        assert provider.model == "gpt-4o"
        assert provider.api_key == "sk-test"

    def test_get_executor_provider_cloud_anthropic(self):
        config = DemoConfig(
            llm_mode=LLMMode.CLOUD,
            cloud_llm=CloudLLMConfig(
                executor_provider="anthropic",
                executor_model="claude-3-haiku",
                anthropic_api_key="sk-ant-test",
            ),
        )
        provider = get_provider_for_role(config, "executor")

        assert isinstance(provider, AnthropicProvider)
        assert provider.model == "claude-3-haiku"
        assert provider.api_key == "sk-ant-test"

    def test_get_provider_string_role(self):
        config = DemoConfig(llm_mode=LLMMode.LOCAL)
        provider = get_provider_for_role(config, "planner")

        assert isinstance(provider, OllamaProvider)

    def test_get_provider_unknown_role(self):
        config = DemoConfig()
        with pytest.raises(ValueError, match="is not a valid Role"):
            get_provider_for_role(config, "unknown")


class TestValidateProviderConfig:
    """Tests for validate_provider_config function."""

    def test_local_mode_no_errors(self):
        config = DemoConfig(llm_mode=LLMMode.LOCAL)
        errors = validate_provider_config(config)
        assert errors == []

    def test_cloud_mode_with_api_keys(self):
        config = DemoConfig(
            llm_mode=LLMMode.CLOUD,
            cloud_llm=CloudLLMConfig(
                planner_provider="openai",
                executor_provider="openai",
                openai_api_key="sk-test",
            ),
        )
        errors = validate_provider_config(config)
        assert errors == []

    def test_cloud_mode_missing_planner_key(self):
        config = DemoConfig(
            llm_mode=LLMMode.CLOUD,
            cloud_llm=CloudLLMConfig(
                planner_provider="openai",
                executor_provider="openai",
                # No API key set
            ),
        )
        errors = validate_provider_config(config)
        assert len(errors) == 1
        assert "planner provider" in errors[0].lower()
        assert "openai" in errors[0].lower()

    def test_cloud_mode_missing_different_keys(self):
        config = DemoConfig(
            llm_mode=LLMMode.CLOUD,
            cloud_llm=CloudLLMConfig(
                planner_provider="openai",
                executor_provider="anthropic",
                # No API keys set
            ),
        )
        errors = validate_provider_config(config)
        assert len(errors) == 2
        assert any("openai" in e.lower() for e in errors)
        assert any("anthropic" in e.lower() for e in errors)

    def test_cloud_mode_same_provider_one_error(self):
        """When planner and executor use the same provider, only one error should appear."""
        config = DemoConfig(
            llm_mode=LLMMode.CLOUD,
            cloud_llm=CloudLLMConfig(
                planner_provider="anthropic",
                executor_provider="anthropic",
                # No API key set
            ),
        )
        errors = validate_provider_config(config)
        # Should only have one error since both use anthropic
        assert len(errors) == 1
        assert "anthropic" in errors[0].lower()


class TestProviderIntegration:
    """Integration tests for provider selection."""

    def test_mixed_provider_setup(self):
        """Test a realistic mixed-provider configuration."""
        config = DemoConfig(
            llm_mode=LLMMode.CLOUD,
            cloud_llm=CloudLLMConfig(
                planner_provider="anthropic",
                planner_model="claude-3-opus",
                executor_provider="openai",
                executor_model="gpt-4o-mini",
                openai_api_key="sk-openai",
                anthropic_api_key="sk-anthropic",
            ),
        )

        planner = get_provider_for_role(config, "planner")
        executor = get_provider_for_role(config, "executor")

        assert isinstance(planner, AnthropicProvider)
        assert planner.model == "claude-3-opus"
        assert planner.api_key == "sk-anthropic"

        assert isinstance(executor, OpenAIProvider)
        assert executor.model == "gpt-4o-mini"
        assert executor.api_key == "sk-openai"

    def test_local_mode_uses_same_ollama(self):
        """Test that local mode uses Ollama for both roles."""
        config = DemoConfig(
            llm_mode=LLMMode.LOCAL,
            ollama=OllamaConfig(
                base_url="http://localhost:11434",
                planner_model="llama3:8b",
                executor_model="phi3:mini",
            ),
        )

        planner = get_provider_for_role(config, "planner")
        executor = get_provider_for_role(config, "executor")

        assert isinstance(planner, OllamaProvider)
        assert isinstance(executor, OllamaProvider)
        assert planner.base_url == executor.base_url
        assert planner.model != executor.model
