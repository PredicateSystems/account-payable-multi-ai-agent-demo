"""Demo workflow using PlannerExecutorAgent for Account Payable Demo.

This module implements the 4-beat demo workflow aligned with the finance demo story:

1. Normal action - Open invoice, compare fields, add note
2. Mark Reconciled - Click appears to work but state doesn't change (silent failure)
3. Release Payment - Risky action blocked by policy (pre-action authorization denial)
4. Route To Review - Safe fallback action succeeds

Browser target: https://www.localllamaland.com/demo/finance/queue

The key demo moments:
- "The agent clicked the button, but the state never changed" (Beat 2)
- "The policy denied the risky action before execution" (Beat 3)
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

# SDK imports from predicate-runtime
from predicate import (
    AgentRuntime,
    AnthropicProvider,
    AsyncPredicateBrowser,
    DeepInfraProvider,
    JsonlTraceSink,
    LLMProvider,
    OpenAIProvider,
    # Verification predicates
    Predicate,
    Tracer,
    any_of,
    create_tracer,
    exists,
    url_contains,
)
from predicate.agents import (
    AutomationTask,
    PlannerExecutorAgent,
    PlannerExecutorConfig,
    RunOutcome,
    TaskCategory,
)
from predicate.backends.playwright_backend import PlaywrightBackend
from predicate.models import SnapshotOptions

from account_payable_demo.authorization import (
    ActionAuthorizer,
    AuthorizationResult,
    DemoAction,
    create_demo_authorizer,
    get_principal_for_beat,
)
from account_payable_demo.config import DemoConfig

logger = logging.getLogger(__name__)


class DemoBeat(str, Enum):
    """Demo workflow beats aligned with finance demo story."""

    OPEN_AND_NOTE = "open_and_note"
    MARK_RECONCILED = "mark_reconciled"  # Silent failure - state doesn't change
    RELEASE_PAYMENT = "release_payment"  # Risky action - blocked by policy
    ROUTE_TO_REVIEW = "route_to_review"  # Safe fallback - succeeds


@dataclass
class BeatResult:
    """Result of executing a demo beat."""

    beat: DemoBeat
    success: bool
    outcome: Optional[RunOutcome] = None
    error: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)
    authorization: Optional[AuthorizationResult] = None

    @property
    def was_policy_blocked(self) -> bool:
        """Check if this beat was blocked by policy."""
        return self.authorization is not None and self.authorization.denied


@dataclass
class WorkflowResult:
    """Result of the complete demo workflow."""

    beats: list[BeatResult] = field(default_factory=list)
    total_tokens: int = 0
    trace_file: Optional[Path] = None
    authorization_log: list[AuthorizationResult] = field(default_factory=list)

    @property
    def all_succeeded(self) -> bool:
        """Check if all beats completed as expected."""
        return all(b.success for b in self.beats)

    @property
    def policy_denials(self) -> list[AuthorizationResult]:
        """Get all policy denials from the workflow."""
        return [r for r in self.authorization_log if r.denied]

    @property
    def policy_allows(self) -> list[AuthorizationResult]:
        """Get all allowed actions from the workflow."""
        return [r for r in self.authorization_log if r.allowed]


def create_sdk_provider(config: DemoConfig, role: str) -> LLMProvider:
    """
    Create an SDK LLMProvider instance from demo config.

    Args:
        config: Demo configuration
        role: "planner" or "executor"

    Returns:
        SDK LLMProvider instance
    """
    if role == "planner":
        provider_name = config.get_planner_provider()
        model = config.get_planner_model()
    else:
        provider_name = config.get_executor_provider()
        model = config.get_executor_model()

    if provider_name == "ollama":
        # Ollama uses OpenAI-compatible API
        return OpenAIProvider(
            model=model,
            base_url=f"{config.ollama.base_url}/v1",
            api_key="ollama",  # Ollama doesn't need real API key
        )
    elif provider_name == "openai":
        return OpenAIProvider(
            model=model,
            api_key=config.cloud_llm.openai_api_key,
        )
    elif provider_name == "anthropic":
        return AnthropicProvider(
            model=model,
            api_key=config.cloud_llm.anthropic_api_key,
        )
    elif provider_name == "deepinfra":
        return DeepInfraProvider(
            model=model,
            api_key=config.cloud_llm.deepinfra_api_key,
        )
    else:
        raise ValueError(f"Unsupported provider: {provider_name}")


# ---------------------------------------------------------------------------
# Verification Predicates (Hard Outcomes)
# ---------------------------------------------------------------------------


def get_beat_1_verification() -> list[Predicate]:
    """
    Beat 1: Open invoice, compare fields, add note.

    Verification: Note was successfully added to the invoice.
    """
    return [
        url_contains("/demo/finance/invoices/"),
        exists("[data-testid='invoice-notes'], .invoice-notes, .notes-section"),
    ]


def get_beat_2_verification() -> list[Predicate]:
    """
    Beat 2: Mark Reconciled - silent failure detection.

    Verification: Status indicator should show "reconciled" but it won't change.
    This predicate is expected to FAIL because the UI doesn't update.
    """
    return [
        exists("[data-status='reconciled'], .status-reconciled, .reconciled-badge"),
    ]


def get_beat_3_verification() -> list[Predicate]:
    """
    Beat 3: Release Payment - risky action blocked by policy.

    Verification: Either a success confirmation OR a policy block message.
    The policy should block this, so we expect policy-denied indicators.
    """
    return [
        any_of(
            exists(".payment-released, [data-testid='payment-success']"),
            exists(".policy-denied, .action-blocked, [data-testid='policy-block']"),
        ),
    ]


def get_beat_4_verification() -> list[Predicate]:
    """
    Beat 4: Route To Review - safe fallback action.

    Verification: Invoice status changed to "pending review" or similar.
    """
    return [
        any_of(
            exists("[data-status='review'], .status-review, .pending-review"),
            exists(".review-requested, [data-testid='review-success']"),
            url_contains("/review"),
        ),
    ]


# ---------------------------------------------------------------------------
# Task Definitions (Soft Plans - LLM generates the steps)
# ---------------------------------------------------------------------------


def get_beat_1_task() -> AutomationTask:
    """
    Beat 1: Open invoice and add a note.

    Task objective given to the planner. The planner decides HOW to accomplish it.
    """
    return AutomationTask(
        task_id="beat-1-open-and-note",
        starting_url="https://www.localllamaland.com/demo/finance/queue",
        task=(
            "Navigate to the finance queue, select the first invoice with exceptions, "
            "open its detail view, compare the invoice amount with the PO amount, "
            "and add a note explaining any discrepancy found."
        ),
        goal={"action": "add_note", "verify": "note_visible"},
        category=TaskCategory.FORM_FILL,
        max_steps=10,
    )


def get_beat_2_task() -> AutomationTask:
    """
    Beat 2: Mark invoice as reconciled (will silently fail).

    The UI will show the button click happening, but the status won't change.
    This demonstrates silent failure detection.
    """
    return AutomationTask(
        task_id="beat-2-mark-reconciled",
        starting_url="https://www.localllamaland.com/demo/finance/queue",
        task=(
            "Navigate to the invoice detail view and click the 'Mark Reconciled' button "
            "to mark this invoice as reconciled. Verify the status indicator updates."
        ),
        goal={"action": "mark_reconciled", "verify": "status_changed"},
        category=TaskCategory.FORM_FILL,
        max_steps=8,
    )


def get_beat_3_task() -> AutomationTask:
    """
    Beat 3: Attempt to release payment (risky - will be blocked).

    The policy should deny this action because the invoice hasn't been properly reviewed.
    """
    return AutomationTask(
        task_id="beat-3-release-payment",
        starting_url="https://www.localllamaland.com/demo/finance/queue",
        task=(
            "Navigate to the invoice detail view and attempt to release payment "
            "by clicking the 'Release Payment' or 'Approve Payment' button."
        ),
        goal={"action": "release_payment"},
        category=TaskCategory.TRANSACTION,
        max_steps=8,
    )


def get_beat_4_task() -> AutomationTask:
    """
    Beat 4: Route to review (safe fallback).

    After the risky action is blocked, fall back to the safe action of routing
    the invoice to a manager for review.
    """
    return AutomationTask(
        task_id="beat-4-route-to-review",
        starting_url="https://www.localllamaland.com/demo/finance/queue",
        task=(
            "Navigate to the invoice detail view and route this invoice to manager review "
            "by clicking 'Route to Review', 'Request Review', or 'Escalate' button."
        ),
        goal={"action": "route_to_review", "verify": "review_requested"},
        category=TaskCategory.FORM_FILL,
        max_steps=8,
    )


# ---------------------------------------------------------------------------
# Workflow Execution
# ---------------------------------------------------------------------------


def get_beat_action(beat: DemoBeat) -> DemoAction:
    """Map a demo beat to its primary action for authorization."""
    action_map = {
        DemoBeat.OPEN_AND_NOTE: DemoAction.ADD_NOTE,
        DemoBeat.MARK_RECONCILED: DemoAction.MARK_RECONCILED,
        DemoBeat.RELEASE_PAYMENT: DemoAction.RELEASE_PAYMENT,
        DemoBeat.ROUTE_TO_REVIEW: DemoAction.ROUTE_TO_REVIEW,
    }
    return action_map[beat]


async def execute_beat(
    agent: PlannerExecutorAgent,
    runtime: AgentRuntime,
    beat: DemoBeat,
    task: AutomationTask,
    verification: list[Predicate],
    authorizer: Optional[ActionAuthorizer] = None,
) -> BeatResult:
    """
    Execute a single demo beat with pre-action authorization.

    Args:
        agent: PlannerExecutorAgent instance
        runtime: AgentRuntime with browser context
        beat: Which beat to execute
        task: AutomationTask for this beat (planner generates the plan)
        verification: Hard predicates for outcome verification
        authorizer: Optional ActionAuthorizer for pre-action checks

    Returns:
        BeatResult with execution details
    """
    # Get beat-specific principal for role-based authorization
    beat_principal = get_principal_for_beat(beat.value)
    logger.info(f"Executing beat: {beat.value} as {beat_principal.value}")
    logger.info(f"Task: {task.task}")

    # Pre-action authorization check
    auth_result: Optional[AuthorizationResult] = None
    if authorizer is not None:
        action = get_beat_action(beat)
        auth_result = authorizer.authorize_beat_action(
            beat_name=beat.value,
            action=action,
            principal=beat_principal,
        )

        if auth_result.denied:
            # Log the denial prominently
            logger.warning("=" * 60)
            logger.warning("POLICY DENIAL - Action blocked before execution")
            logger.warning("=" * 60)
            logger.warning(f"Beat: {beat.value}")
            logger.warning(f"Action: {auth_result.action}")
            logger.warning(f"Resource: {auth_result.resource}")
            logger.warning(f"Reason: {auth_result.reason.value}")
            if auth_result.violated_rule:
                logger.warning(f"Violated Rule: {auth_result.violated_rule}")
            logger.warning("=" * 60)

            # For Beat 3 (Release Payment), denial is expected and counts as success
            if beat == DemoBeat.RELEASE_PAYMENT:
                return BeatResult(
                    beat=beat,
                    success=True,  # Denial was expected
                    authorization=auth_result,
                    details={
                        "policy_blocked": True,
                        "violated_rule": auth_result.violated_rule,
                        "reason": auth_result.reason.value,
                    },
                )
            else:
                # Unexpected denial for other beats
                return BeatResult(
                    beat=beat,
                    success=False,
                    authorization=auth_result,
                    error=f"Unexpected policy denial: {auth_result.violated_rule}",
                    details={
                        "policy_blocked": True,
                        "violated_rule": auth_result.violated_rule,
                        "reason": auth_result.reason.value,
                    },
                )

    try:
        # Execute the task - agent generates plan and executes
        outcome = await agent.run(
            runtime=runtime,
            task=task,
        )

        # Verify the expected outcome using hard predicates
        verification_passed = True
        for pred in verification:
            ctx = runtime._ctx()
            result = pred.evaluate(ctx)
            if not result.passed:
                logger.warning(f"Verification predicate failed: {pred}")
                verification_passed = False
                break

        # Determine success based on beat type and expected behavior
        if beat == DemoBeat.OPEN_AND_NOTE:
            # Beat 1: Should complete successfully with verification passing
            success = verification_passed
        elif beat == DemoBeat.MARK_RECONCILED:
            # Beat 2: Expected to fail verification (silent failure demo)
            # Success for the demo = verification correctly detects the failure
            success = not verification_passed
        elif beat == DemoBeat.RELEASE_PAYMENT:
            # Beat 3: Should have been blocked by policy (handled above)
            # If we get here, policy didn't block - check verification
            success = outcome.fallback_used or not verification_passed
        elif beat == DemoBeat.ROUTE_TO_REVIEW:
            # Beat 4: Should complete successfully
            success = verification_passed
        else:
            success = False

        return BeatResult(
            beat=beat,
            success=success,
            outcome=outcome,
            authorization=auth_result,
            details={
                "verification_passed": verification_passed,
                "fallback_used": outcome.fallback_used,
                "error": outcome.error,
                "total_duration_ms": outcome.total_duration_ms,
                "policy_blocked": False,
            },
        )

    except Exception as e:
        logger.error(f"Beat {beat.value} failed with error: {e}")
        return BeatResult(
            beat=beat,
            success=False,
            error=str(e),
            authorization=auth_result,
        )


async def run_demo_workflow(
    config: DemoConfig,
    headless: bool = True,
    policy_file: Optional[Path] = None,
    enable_authorization: bool = True,
) -> WorkflowResult:
    """
    Run the complete 4-beat demo workflow with authorization.

    Args:
        config: Demo configuration
        headless: Run browser in headless mode
        policy_file: Path to policy file (defaults to policy.yaml in demo root)
        enable_authorization: Whether to enable pre-action authorization

    Returns:
        WorkflowResult with all beat results and authorization log
    """
    result = WorkflowResult()

    # Set up trace file
    trace_dir = config.trace_output_dir
    trace_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(uuid.uuid4())
    trace_file = trace_dir / f"demo-workflow-{run_id}.jsonl"
    result.trace_file = trace_file

    # Create authorizer if enabled
    authorizer: Optional[ActionAuthorizer] = None
    if enable_authorization:
        try:
            authorizer = create_demo_authorizer(policy_file)
            logger.info("Authorization enabled with policy file")
        except FileNotFoundError as e:
            logger.warning(f"Policy file not found, running without authorization: {e}")
        except Exception as e:
            logger.warning(f"Failed to create authorizer, running without authorization: {e}")

    # Create SDK providers
    planner = create_sdk_provider(config, "planner")
    executor = create_sdk_provider(config, "executor")

    # Create tracer - use cloud tracing if PREDICATE_API_KEY is set
    if config.has_predicate_api_key:
        logger.info("Using Predicate cloud tracing")
        tracer = create_tracer(
            api_key=config.predicate_api_key,
            run_id=run_id,
            api_url=config.predicate_api_url,
            goal="Account Payable Demo - Finance Workflow",
            agent_type="planner-executor",
            llm_model=config.get_planner_model(),
            start_url=config.app.finance_queue_url,
        )
    else:
        # Fall back to local file tracing
        logger.info("Using local file tracing (set PREDICATE_API_KEY for cloud tracing)")
        sink = JsonlTraceSink(trace_file)
        tracer = Tracer(run_id=run_id, sink=sink)

    # Create agent config with correct SDK API
    agent_config = PlannerExecutorConfig(
        verbose=config.debug,
    )

    # Create agent
    agent = PlannerExecutorAgent(
        planner=planner,
        executor=executor,
        config=agent_config,
        tracer=tracer,
    )

    # Define beats with their tasks and verification predicates
    beats = [
        (DemoBeat.OPEN_AND_NOTE, get_beat_1_task(), get_beat_1_verification()),
        (DemoBeat.MARK_RECONCILED, get_beat_2_task(), get_beat_2_verification()),
        (DemoBeat.RELEASE_PAYMENT, get_beat_3_task(), get_beat_3_verification()),
        (DemoBeat.ROUTE_TO_REVIEW, get_beat_4_task(), get_beat_4_verification()),
    ]

    # Determine if we should use API features
    use_api = config.has_predicate_api_key

    # Configure SnapshotOptions with show_overlay and API key
    snapshot_options = SnapshotOptions(
        limit=60,
        screenshot=True,
        show_overlay=config.show_overlay,
        goal="Account Payable Demo - Finance Workflow",
        use_api=True if use_api else None,
        predicate_api_key=config.predicate_api_key if use_api else None,
    )

    # Log API usage status
    if use_api:
        logger.info("Using Predicate API for snapshots (show_overlay enabled)")
    else:
        logger.info(f"Using local snapshots (show_overlay={config.show_overlay})")

    # Use AsyncPredicateBrowser for better snapshot integration
    async with AsyncPredicateBrowser(
        api_key=config.predicate_api_key,
        headless=headless,
    ) as browser:
        page = browser.page

        # Navigate to starting URL
        await page.goto(config.app.finance_queue_url)
        await page.wait_for_load_state("domcontentloaded", timeout=15_000)
        try:
            await page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            pass  # Best effort

        # Create runtime with PlaywrightBackend and API key
        backend = PlaywrightBackend(page)
        runtime = AgentRuntime(
            backend=backend,
            tracer=tracer,
            predicate_api_key=config.predicate_api_key,
            snapshot_options=snapshot_options,
        )

        # Execute each beat
        for beat, task, verification in beats:
            logger.info(f"\n{'=' * 60}")
            logger.info(f"Starting {beat.value}")
            logger.info(f"{'=' * 60}")

            beat_result = await execute_beat(
                agent=agent,
                runtime=runtime,
                beat=beat,
                task=task,
                verification=verification,
                authorizer=authorizer,
            )
            result.beats.append(beat_result)

            # Log beat result
            if beat_result.was_policy_blocked:
                logger.info(f"Beat {beat.value} was BLOCKED by policy")
                logger.info(f"  Rule: {beat_result.authorization.violated_rule}")
                logger.info(f"  Expected: {beat_result.success}")
            elif beat_result.outcome:
                logger.info(f"Beat {beat.value} completed")
                logger.info(
                    f"  Verification: {'PASS' if beat_result.details.get('verification_passed') else 'FAIL'}"
                )
                logger.info(f"  Expected success: {beat_result.success}")
            if beat_result.error:
                logger.error(f"Beat {beat.value} error: {beat_result.error}")

    # Collect authorization log
    if authorizer is not None:
        result.authorization_log = authorizer.get_authorization_log()

    # Collect token usage
    if result.beats and result.beats[0].outcome:
        token_usage = result.beats[0].outcome.token_usage
        if token_usage:
            result.total_tokens = token_usage.get("total", {}).get("total_tokens", 0)

    return result


def print_workflow_result(result: WorkflowResult) -> None:
    """Print a formatted summary of the workflow result."""
    print("\n" + "=" * 70)
    print(" Demo Workflow Results")
    print("=" * 70)

    beat_descriptions = {
        DemoBeat.OPEN_AND_NOTE: "Open invoice and add note",
        DemoBeat.MARK_RECONCILED: "Mark Reconciled (silent failure expected)",
        DemoBeat.RELEASE_PAYMENT: "Release Payment (policy block expected)",
        DemoBeat.ROUTE_TO_REVIEW: "Route To Review (safe fallback)",
    }

    for beat_result in result.beats:
        status = "PASS" if beat_result.success else "FAIL"
        desc = beat_descriptions.get(beat_result.beat, beat_result.beat.value)
        print(f"\n{beat_result.beat.value}:")
        print(f"  Description: {desc}")
        print(f"  Status: {status}")

        # Show authorization result if present
        if beat_result.was_policy_blocked:
            print("  POLICY BLOCKED: Yes")
            print(f"  Violated Rule: {beat_result.authorization.violated_rule}")
            print(f"  Denial Reason: {beat_result.authorization.reason.value}")
        elif beat_result.authorization and beat_result.authorization.allowed:
            print("  Authorization: ALLOWED")

        if beat_result.details:
            if "verification_passed" in beat_result.details:
                print(
                    f"  Verification passed: {beat_result.details.get('verification_passed', 'N/A')}"
                )
            if "total_duration_ms" in beat_result.details:
                print(f"  Duration: {beat_result.details.get('total_duration_ms', 'N/A')}ms")
        if beat_result.error:
            print(f"  Error: {beat_result.error}")

    # Authorization summary
    if result.authorization_log:
        print(f"\n{'=' * 70}")
        print(" Authorization Summary")
        print("=" * 70)
        print(f"Total authorization checks: {len(result.authorization_log)}")
        print(f"Allowed: {len(result.policy_allows)}")
        print(f"Denied: {len(result.policy_denials)}")

        if result.policy_denials:
            print("\nDenied Actions:")
            for denial in result.policy_denials:
                print(f"  - {denial.action} on {denial.resource}")
                print(f"    Rule: {denial.violated_rule}")

    print(f"\n{'=' * 70}")
    print(f"Total tokens used: {result.total_tokens}")
    if result.trace_file:
        print(f"Trace file: {result.trace_file}")
    print(f"All beats succeeded as expected: {result.all_succeeded}")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Exported helpers for testing (minimal - tests should focus on outcomes)
# ---------------------------------------------------------------------------


def build_predicate_spec(predicate_type: str, **kwargs: Any) -> dict[str, Any]:
    """
    Build a predicate specification dict for testing purposes.

    Note: In the soft-plans design, the agent generates its own predicates.
    This helper is for testing verification logic only.
    """
    return {
        "predicate": predicate_type,
        "args": list(kwargs.values()),
        **kwargs,
    }


def build_demo_plan_step(
    step_id: int,
    goal: str,
    action: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """
    Build a plan step dict for testing purposes.

    Note: In the soft-plans design, the planner generates steps.
    This helper is for testing plan structures only.
    """
    return {
        "id": step_id,
        "goal": goal,
        "action": action.upper(),
        **kwargs,
    }
