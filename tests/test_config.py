"""Tests for configuration loading and parsing."""

from __future__ import annotations

from pathlib import Path

from account_payable_demo.config import (
    AppConfig,
    CloudLLMConfig,
    DemoConfig,
    LLMMode,
    OllamaConfig,
    RunMode,
    SidecarConfig,
    load_config,
)


class TestRunMode:
    """Tests for RunMode enum."""

    def test_local_mode_value(self):
        assert RunMode.LOCAL.value == "local"

    def test_docker_mode_value(self):
        assert RunMode.DOCKER.value == "docker"

    def test_from_string(self):
        assert RunMode("local") == RunMode.LOCAL
        assert RunMode("docker") == RunMode.DOCKER


class TestLLMMode:
    """Tests for LLMMode enum."""

    def test_cloud_mode_value(self):
        assert LLMMode.CLOUD.value == "cloud"

    def test_local_mode_value(self):
        assert LLMMode.LOCAL.value == "local"

    def test_from_string(self):
        assert LLMMode("cloud") == LLMMode.CLOUD
        assert LLMMode("local") == LLMMode.LOCAL


class TestOllamaConfig:
    """Tests for OllamaConfig."""

    def test_default_values(self):
        config = OllamaConfig()
        assert config.base_url == "http://localhost:11434"
        assert config.planner_model == "qwen2.5:7b-instruct"
        assert config.executor_model == "qwen2.5:4b-instruct"

    def test_custom_values(self):
        config = OllamaConfig(
            base_url="http://custom:1234",
            planner_model="llama3:8b",
            executor_model="llama3:3b",
        )
        assert config.base_url == "http://custom:1234"
        assert config.planner_model == "llama3:8b"
        assert config.executor_model == "llama3:3b"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://test:5555")
        monkeypatch.setenv("OLLAMA_PLANNER_MODEL", "mistral:7b")
        monkeypatch.setenv("OLLAMA_EXECUTOR_MODEL", "phi3:mini")

        config = OllamaConfig.from_env()
        assert config.base_url == "http://test:5555"
        assert config.planner_model == "mistral:7b"
        assert config.executor_model == "phi3:mini"


class TestCloudLLMConfig:
    """Tests for CloudLLMConfig."""

    def test_default_values(self):
        config = CloudLLMConfig()
        assert config.planner_provider == "openai"
        assert config.planner_model == "gpt-4o"
        assert config.executor_provider == "openai"
        assert config.executor_model == "gpt-4o-mini"

    def test_get_api_key_openai(self):
        config = CloudLLMConfig(openai_api_key="sk-test")
        assert config.get_api_key("openai") == "sk-test"
        assert config.get_api_key("OpenAI") == "sk-test"

    def test_get_api_key_anthropic(self):
        config = CloudLLMConfig(anthropic_api_key="sk-ant-test")
        assert config.get_api_key("anthropic") == "sk-ant-test"

    def test_get_api_key_deepinfra(self):
        config = CloudLLMConfig(deepinfra_api_key="di-test")
        assert config.get_api_key("deepinfra") == "di-test"

    def test_get_api_key_unknown_provider(self):
        config = CloudLLMConfig()
        assert config.get_api_key("unknown") is None

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("PLANNER_PROVIDER", "anthropic")
        monkeypatch.setenv("PLANNER_MODEL", "claude-3-opus")
        monkeypatch.setenv("EXECUTOR_PROVIDER", "openai")
        monkeypatch.setenv("EXECUTOR_MODEL", "gpt-4o-mini")
        monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anthropic")

        config = CloudLLMConfig.from_env()
        assert config.planner_provider == "anthropic"
        assert config.planner_model == "claude-3-opus"
        assert config.executor_provider == "openai"
        assert config.executor_model == "gpt-4o-mini"
        assert config.openai_api_key == "sk-openai"
        assert config.anthropic_api_key == "sk-anthropic"


class TestSidecarConfig:
    """Tests for SidecarConfig."""

    def test_default_values(self):
        config = SidecarConfig()
        assert config.url == "http://localhost:8787"
        assert config.policy_path == Path("./policy.yaml")
        assert config.version == "latest"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("PREDICATE_SIDECAR_URL", "http://sidecar:9000")
        monkeypatch.setenv("SIDECAR_POLICY_PATH", "/etc/policy.yaml")
        monkeypatch.setenv("SIDECAR_VERSION", "v1.2.3")

        config = SidecarConfig.from_env()
        assert config.url == "http://sidecar:9000"
        assert config.policy_path == Path("/etc/policy.yaml")
        assert config.version == "v1.2.3"

    def test_from_env_with_base_dir(self, monkeypatch):
        monkeypatch.setenv("SIDECAR_POLICY_PATH", "./custom/policy.yaml")

        base_dir = Path("/home/user/demo")
        config = SidecarConfig.from_env(base_dir)
        assert config.policy_path == Path("/home/user/demo/custom/policy.yaml")


class TestAppConfig:
    """Tests for AppConfig."""

    def test_default_values(self):
        config = AppConfig()
        assert config.base_url == "https://www.localllamaland.com"
        assert config.finance_queue_url == "https://www.localllamaland.com/demo/finance/queue"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("APP_BASE_URL", "http://localhost:3000")
        monkeypatch.setenv("FINANCE_QUEUE_URL", "http://localhost:3000/finance")

        config = AppConfig.from_env()
        assert config.base_url == "http://localhost:3000"
        assert config.finance_queue_url == "http://localhost:3000/finance"

    def test_from_env_derives_queue_url(self, monkeypatch):
        monkeypatch.setenv("APP_BASE_URL", "http://localhost:3000")
        # Don't set FINANCE_QUEUE_URL - it should be derived

        config = AppConfig.from_env()
        assert config.base_url == "http://localhost:3000"
        assert config.finance_queue_url == "http://localhost:3000/demo/finance/queue"


class TestDemoConfig:
    """Tests for DemoConfig."""

    def test_default_values(self):
        config = DemoConfig()
        assert config.run_mode == RunMode.LOCAL
        assert config.llm_mode == LLMMode.CLOUD
        assert config.headless is False
        assert config.debug is False

    def test_is_local_llm(self):
        config = DemoConfig(llm_mode=LLMMode.LOCAL)
        assert config.is_local_llm is True
        assert config.is_cloud_llm is False

    def test_is_cloud_llm(self):
        config = DemoConfig(llm_mode=LLMMode.CLOUD)
        assert config.is_local_llm is False
        assert config.is_cloud_llm is True

    def test_is_docker_mode(self):
        config = DemoConfig(run_mode=RunMode.DOCKER)
        assert config.is_docker_mode is True

    def test_get_planner_model_local(self):
        config = DemoConfig(
            llm_mode=LLMMode.LOCAL,
            ollama=OllamaConfig(planner_model="llama3:8b"),
        )
        assert config.get_planner_model() == "llama3:8b"

    def test_get_planner_model_cloud(self):
        config = DemoConfig(
            llm_mode=LLMMode.CLOUD,
            cloud_llm=CloudLLMConfig(planner_model="gpt-4-turbo"),
        )
        assert config.get_planner_model() == "gpt-4-turbo"

    def test_get_executor_model_local(self):
        config = DemoConfig(
            llm_mode=LLMMode.LOCAL,
            ollama=OllamaConfig(executor_model="phi3:mini"),
        )
        assert config.get_executor_model() == "phi3:mini"

    def test_get_executor_model_cloud(self):
        config = DemoConfig(
            llm_mode=LLMMode.CLOUD,
            cloud_llm=CloudLLMConfig(executor_model="gpt-3.5-turbo"),
        )
        assert config.get_executor_model() == "gpt-3.5-turbo"

    def test_get_planner_provider_local(self):
        config = DemoConfig(llm_mode=LLMMode.LOCAL)
        assert config.get_planner_provider() == "ollama"

    def test_get_planner_provider_cloud(self):
        config = DemoConfig(
            llm_mode=LLMMode.CLOUD,
            cloud_llm=CloudLLMConfig(planner_provider="anthropic"),
        )
        assert config.get_planner_provider() == "anthropic"

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("RUN_MODE", "docker")
        monkeypatch.setenv("LLM_MODE", "local")
        monkeypatch.setenv("HEADLESS", "true")
        monkeypatch.setenv("DEBUG", "true")

        config = DemoConfig.from_env()
        assert config.run_mode == RunMode.DOCKER
        assert config.llm_mode == LLMMode.LOCAL
        assert config.headless is True
        assert config.debug is True


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_from_env_file(self, tmp_path, monkeypatch):
        # Create a temporary .env file
        env_content = """
LLM_MODE=local
RUN_MODE=docker
OLLAMA_BASE_URL=http://ollama:11434
OLLAMA_PLANNER_MODEL=llama3:8b
DEBUG=true
"""
        env_file = tmp_path / ".env"
        env_file.write_text(env_content)

        # Clear any existing env vars that might interfere
        for key in ["LLM_MODE", "RUN_MODE", "OLLAMA_BASE_URL", "OLLAMA_PLANNER_MODEL", "DEBUG"]:
            monkeypatch.delenv(key, raising=False)

        config = load_config(env_file=env_file, base_dir=tmp_path)

        assert config.llm_mode == LLMMode.LOCAL
        assert config.run_mode == RunMode.DOCKER
        assert config.ollama.base_url == "http://ollama:11434"
        assert config.ollama.planner_model == "llama3:8b"
        assert config.debug is True

    def test_load_with_missing_env_file(self, tmp_path, monkeypatch):
        # Clear env vars
        for key in ["LLM_MODE", "RUN_MODE"]:
            monkeypatch.delenv(key, raising=False)

        # Should use defaults when .env file doesn't exist
        config = load_config(base_dir=tmp_path)

        assert config.llm_mode == LLMMode.CLOUD
        assert config.run_mode == RunMode.LOCAL

    def test_load_resolves_relative_paths(self, tmp_path, monkeypatch):
        env_content = """
TRACE_OUTPUT_DIR=./my_traces
ARTIFACT_OUTPUT_DIR=./my_artifacts
SIDECAR_POLICY_PATH=./policies/demo.yaml
"""
        env_file = tmp_path / ".env"
        env_file.write_text(env_content)

        for key in ["TRACE_OUTPUT_DIR", "ARTIFACT_OUTPUT_DIR", "SIDECAR_POLICY_PATH"]:
            monkeypatch.delenv(key, raising=False)

        config = load_config(env_file=env_file, base_dir=tmp_path)

        assert config.trace_output_dir == tmp_path / "my_traces"
        assert config.artifact_output_dir == tmp_path / "my_artifacts"
        assert config.sidecar.policy_path == tmp_path / "policies" / "demo.yaml"
