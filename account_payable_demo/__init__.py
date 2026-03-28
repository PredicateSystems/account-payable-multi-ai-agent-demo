"""Account Payable Demo - Predicate Systems finance workflow demo."""

from account_payable_demo.config import DemoConfig, load_config
from account_payable_demo.providers import (
    LLMProvider,
    ProviderType,
    create_provider,
    get_provider_for_role,
)
from account_payable_demo.sidecar import (
    LOCAL_BOOTSTRAP_SUPPORTED_OS,
    Architecture,
    OS,
    Platform,
    detect_architecture,
    detect_os,
    detect_platform,
    download_sidecar,
    health_check,
    resolve_download_url,
)

__all__ = [
    # Config
    "DemoConfig",
    "load_config",
    # Providers
    "LLMProvider",
    "ProviderType",
    "create_provider",
    "get_provider_for_role",
    # Sidecar
    "OS",
    "Architecture",
    "Platform",
    "LOCAL_BOOTSTRAP_SUPPORTED_OS",
    "detect_os",
    "detect_architecture",
    "detect_platform",
    "resolve_download_url",
    "download_sidecar",
    "health_check",
]

__version__ = "0.1.0"
