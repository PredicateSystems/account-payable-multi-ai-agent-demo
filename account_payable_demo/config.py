"""Configuration model and loading for the Account Payable Demo."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


class RunMode(str, Enum):
    """Deployment mode for the demo."""

    LOCAL = "local"
    DOCKER = "docker"


class LLMMode(str, Enum):
    """LLM inference mode."""

    CLOUD = "cloud"
    LOCAL = "local"


@dataclass
class OllamaConfig:
    """Configuration for local Ollama-based inference."""

    base_url: str = "http://localhost:11434"
    planner_model: str = "qwen2.5:7b-instruct"
    executor_model: str = "qwen2.5:4b-instruct"

    @classmethod
    def from_env(cls) -> "OllamaConfig":
        """Load Ollama config from environment variables."""
        return cls(
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
            planner_model=os.getenv("OLLAMA_PLANNER_MODEL", "qwen2.5:7b-instruct"),
            executor_model=os.getenv("OLLAMA_EXECUTOR_MODEL", "qwen2.5:4b-instruct"),
        )


@dataclass
class CloudLLMConfig:
    """Configuration for cloud LLM providers."""

    planner_provider: str = "openai"
    planner_model: str = "gpt-4o"
    executor_provider: str = "openai"
    executor_model: str = "gpt-4o-mini"

    # API keys (loaded from env, not stored in config files)
    openai_api_key: Optional[str] = field(default=None, repr=False)
    anthropic_api_key: Optional[str] = field(default=None, repr=False)
    deepinfra_api_key: Optional[str] = field(default=None, repr=False)

    @classmethod
    def from_env(cls) -> "CloudLLMConfig":
        """Load cloud LLM config from environment variables."""
        return cls(
            planner_provider=os.getenv("PLANNER_PROVIDER", "openai"),
            planner_model=os.getenv("PLANNER_MODEL", "gpt-4o"),
            executor_provider=os.getenv("EXECUTOR_PROVIDER", "openai"),
            executor_model=os.getenv("EXECUTOR_MODEL", "gpt-4o-mini"),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
            deepinfra_api_key=os.getenv("DEEPINFRA_API_KEY"),
        )

    def get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for a specific provider."""
        key_map = {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "deepinfra": self.deepinfra_api_key,
        }
        return key_map.get(provider.lower())


@dataclass
class SidecarConfig:
    """Configuration for the Predicate sidecar."""

    url: str = "http://localhost:8787"
    policy_path: Path = field(default_factory=lambda: Path("./policy.yaml"))
    release_repo: str = "PredicateSystems/predicate-authority-sidecar"
    version: str = "latest"

    @classmethod
    def from_env(cls, base_dir: Optional[Path] = None) -> "SidecarConfig":
        """Load sidecar config from environment variables."""
        policy_path_str = os.getenv("SIDECAR_POLICY_PATH", "./policy.yaml")
        policy_path = Path(policy_path_str)

        # Make relative paths relative to base_dir if provided
        if base_dir and not policy_path.is_absolute():
            policy_path = base_dir / policy_path

        return cls(
            url=os.getenv("PREDICATE_SIDECAR_URL", "http://localhost:8787"),
            policy_path=policy_path,
            release_repo=os.getenv(
                "SIDECAR_RELEASE_REPO", "PredicateSystems/predicate-authority-sidecar"
            ),
            version=os.getenv("SIDECAR_VERSION", "latest"),
        )


@dataclass
class AppConfig:
    """Configuration for the target demo application."""

    base_url: str = "https://www.localllamaland.com"
    finance_queue_url: str = "https://www.localllamaland.com/demo/finance/queue"

    @classmethod
    def from_env(cls) -> "AppConfig":
        """Load app config from environment variables."""
        base_url = os.getenv("APP_BASE_URL", "https://www.localllamaland.com")
        finance_queue_url = os.getenv(
            "FINANCE_QUEUE_URL",
            f"{base_url}/demo/finance/queue",
        )
        return cls(
            base_url=base_url,
            finance_queue_url=finance_queue_url,
        )


@dataclass
class DemoConfig:
    """Complete configuration for the Account Payable Demo."""

    run_mode: RunMode = RunMode.LOCAL
    llm_mode: LLMMode = LLMMode.CLOUD

    # Sub-configurations
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    cloud_llm: CloudLLMConfig = field(default_factory=CloudLLMConfig)
    sidecar: SidecarConfig = field(default_factory=SidecarConfig)
    app: AppConfig = field(default_factory=AppConfig)

    # Predicate cloud tracing
    predicate_api_key: Optional[str] = field(default=None, repr=False)
    predicate_api_url: Optional[str] = None

    # Runtime behavior
    headless: bool = False
    debug: bool = False
    show_overlay: bool = True  # Show snapshot overlay in browser (default: True)
    trace_output_dir: Path = field(default_factory=lambda: Path("./traces"))
    artifact_output_dir: Path = field(default_factory=lambda: Path("./artifacts"))

    @classmethod
    def from_env(cls, base_dir: Optional[Path] = None) -> "DemoConfig":
        """Load complete config from environment variables."""
        run_mode_str = os.getenv("RUN_MODE", "local").lower()
        llm_mode_str = os.getenv("LLM_MODE", "cloud").lower()

        trace_dir_str = os.getenv("TRACE_OUTPUT_DIR", "./traces")
        artifact_dir_str = os.getenv("ARTIFACT_OUTPUT_DIR", "./artifacts")

        trace_dir = Path(trace_dir_str)
        artifact_dir = Path(artifact_dir_str)

        if base_dir:
            if not trace_dir.is_absolute():
                trace_dir = base_dir / trace_dir
            if not artifact_dir.is_absolute():
                artifact_dir = base_dir / artifact_dir

        return cls(
            run_mode=RunMode(run_mode_str),
            llm_mode=LLMMode(llm_mode_str),
            ollama=OllamaConfig.from_env(),
            cloud_llm=CloudLLMConfig.from_env(),
            sidecar=SidecarConfig.from_env(base_dir),
            app=AppConfig.from_env(),
            predicate_api_key=os.getenv("PREDICATE_API_KEY"),
            predicate_api_url=os.getenv("PREDICATE_API_URL"),
            headless=os.getenv("HEADLESS", "false").lower() == "true",
            debug=os.getenv("DEBUG", "false").lower() == "true",
            show_overlay=os.getenv("SHOW_OVERLAY", "true").lower() == "true",
            trace_output_dir=trace_dir,
            artifact_output_dir=artifact_dir,
        )

    @property
    def is_local_llm(self) -> bool:
        """Check if using local LLM mode."""
        return self.llm_mode == LLMMode.LOCAL

    @property
    def is_cloud_llm(self) -> bool:
        """Check if using cloud LLM mode."""
        return self.llm_mode == LLMMode.CLOUD

    @property
    def is_docker_mode(self) -> bool:
        """Check if running in Docker mode."""
        return self.run_mode == RunMode.DOCKER

    def get_planner_model(self) -> str:
        """Get the planner model name based on LLM mode."""
        if self.is_local_llm:
            return self.ollama.planner_model
        return self.cloud_llm.planner_model

    def get_executor_model(self) -> str:
        """Get the executor model name based on LLM mode."""
        if self.is_local_llm:
            return self.ollama.executor_model
        return self.cloud_llm.executor_model

    def get_planner_provider(self) -> str:
        """Get the planner provider based on LLM mode."""
        if self.is_local_llm:
            return "ollama"
        return self.cloud_llm.planner_provider

    def get_executor_provider(self) -> str:
        """Get the executor provider based on LLM mode."""
        if self.is_local_llm:
            return "ollama"
        return self.cloud_llm.executor_provider

    @property
    def has_predicate_api_key(self) -> bool:
        """Check if Predicate API key is configured for cloud tracing."""
        return self.predicate_api_key is not None and self.predicate_api_key.strip() != ""


def load_config(
    env_file: Optional[Path] = None,
    base_dir: Optional[Path] = None,
) -> DemoConfig:
    """
    Load configuration from .env file and environment variables.

    Args:
        env_file: Path to .env file. If None, looks for .env in base_dir or cwd.
        base_dir: Base directory for resolving relative paths.

    Returns:
        DemoConfig instance with all configuration loaded.
    """
    if base_dir is None:
        base_dir = Path.cwd()

    if env_file is None:
        env_file = base_dir / ".env"

    # Load .env file if it exists
    if env_file.exists():
        load_dotenv(env_file)

    return DemoConfig.from_env(base_dir)
