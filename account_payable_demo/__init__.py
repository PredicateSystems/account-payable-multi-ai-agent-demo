"""Account Payable Demo - Predicate Systems finance workflow demo."""

from account_payable_demo.authorization import (
    ActionAuthorizer,
    AuthorizationResult,
    DemoAction,
    DemoPrincipal,
    RuntimeAuthorizerCallback,
    create_demo_authorizer,
    create_runtime_authorizer,
    format_denial_message,
    get_principal_for_beat,
)
from account_payable_demo.config import DemoConfig, load_config
from account_payable_demo.providers import (
    LLMProvider,
    ProviderType,
    create_provider,
    get_provider_for_role,
)
from account_payable_demo.sidecar import (
    LOCAL_BOOTSTRAP_SUPPORTED_OS,
    OS,
    Architecture,
    Platform,
    detect_architecture,
    detect_os,
    detect_platform,
    download_sidecar,
    health_check,
    resolve_download_url,
)
from account_payable_demo.workflow import (
    BeatResult,
    DemoBeat,
    WorkflowResult,
    build_demo_plan_step,
    build_predicate_spec,
    create_sdk_provider,
    get_beat_1_task,
    get_beat_1_verification,
    get_beat_2_task,
    get_beat_2_verification,
    get_beat_3_task,
    get_beat_3_verification,
    get_beat_4_task,
    get_beat_4_verification,
    print_workflow_result,
    run_demo_workflow,
)

__all__ = [
    # Authorization
    "ActionAuthorizer",
    "AuthorizationResult",
    "DemoAction",
    "DemoPrincipal",
    "RuntimeAuthorizerCallback",
    "create_demo_authorizer",
    "create_runtime_authorizer",
    "format_denial_message",
    "get_principal_for_beat",
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
    # Workflow
    "DemoBeat",
    "BeatResult",
    "WorkflowResult",
    "build_predicate_spec",
    "build_demo_plan_step",
    "create_sdk_provider",
    "run_demo_workflow",
    "print_workflow_result",
    # Verification predicates (hard outcomes)
    "get_beat_1_verification",
    "get_beat_2_verification",
    "get_beat_3_verification",
    "get_beat_4_verification",
    # Tasks (soft plans)
    "get_beat_1_task",
    "get_beat_2_task",
    "get_beat_3_task",
    "get_beat_4_task",
]

__version__ = "0.1.0"
