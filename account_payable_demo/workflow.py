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

# SDK imports from predicate-runtime (use explicit submodule imports for compatibility)
from predicate import AsyncPredicateBrowser, create_tracer
from predicate.agent_runtime import AgentRuntime
from predicate.agents import (
    AutomationTask,
    ModalDismissalConfig,
    PlannerExecutorAgent,
    PlannerExecutorConfig,
    RunOutcome,
    SnapshotEscalationConfig,
    StepwisePlanningConfig,
    TaskCategory,
)
from predicate.agents.planner_executor_agent import RetryConfig
from predicate.backends.playwright_backend import PlaywrightBackend
from predicate.llm_provider import (
    AnthropicProvider,
    DeepInfraProvider,
    LLMProvider,
    OllamaProvider,
    OpenAIProvider,
)
from predicate.models import ScreenshotConfig, SnapshotOptions
from predicate.verification import Predicate, exists, url_contains

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
        # Use the new OllamaProvider which wraps OpenAI-compatible API
        return OllamaProvider(
            model=model,
            base_url=config.ollama.base_url,
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
# Finance Demo Heuristics (Domain-Specific Element Selection)
# ---------------------------------------------------------------------------


class FinanceHeuristics:
    """
    Domain-specific heuristics for LocalLlamaLand finance demo.

    These heuristics help the executor find elements without LLM calls
    for common finance workflow patterns on the demo site.
    """

    def find_element_for_intent(
        self,
        intent: str,
        elements: list[Any],
        url: str,
        goal: str,
    ) -> int | None:
        """Find element ID using domain-specific heuristics."""
        intent_lower = intent.lower().replace("-", "_").replace(" ", "_")
        goal_lower = goal.lower() if goal else ""

        # Invoice selection in queue (also match specific invoice IDs like INV-2024-001)
        if (
            "invoice" in intent_lower
            or "exception" in intent_lower
            or intent_lower.startswith("inv_")
        ):
            return self._find_invoice_row(elements, url, intent)

        # Add note button/field - check both intent and goal
        if "note" in intent_lower or "add_note" in intent_lower or "note" in goal_lower:
            return self._find_add_note_element(elements)

        # Mark reconciled button - check both intent and goal
        if "reconcil" in intent_lower or "reconcil" in goal_lower:
            return self._find_reconcile_button(elements)

        # Release payment button - check both intent and goal
        if (
            "release" in intent_lower
            or "payment" in intent_lower
            or "release" in goal_lower
            or "payment" in goal_lower
        ):
            return self._find_release_payment_button(elements)

        # Route to review button - check both intent and goal
        if (
            "review" in intent_lower
            or "route" in intent_lower
            or "escalate" in intent_lower
            or "review" in goal_lower
            or "route" in goal_lower
        ):
            return self._find_route_to_review_button(elements)

        # Submit/save button
        if "submit" in intent_lower or "save" in intent_lower:
            return self._find_submit_button(elements)

        # Textbox/textarea for TYPE_AND_SUBMIT - check goal for context
        if intent_lower in {"textbox", "textarea", "input", "field", "text_field", "input_field"}:
            # Use goal to determine what kind of textbox
            if "note" in goal_lower or "comment" in goal_lower:
                return self._find_note_textbox(elements)
            # Generic textbox - find first visible one
            return self._find_first_textbox(elements)

        # Fallback: if intent is generic ("button", "link") but goal contains specific action keywords
        if intent_lower in {"button", "link", "element"}:
            if "note" in goal_lower:
                return self._find_add_note_element(elements)
            if "reconcil" in goal_lower:
                return self._find_reconcile_button(elements)
            if "release" in goal_lower or "payment" in goal_lower:
                return self._find_release_payment_button(elements)
            if "review" in goal_lower or "route" in goal_lower:
                return self._find_route_to_review_button(elements)

        return None

    def priority_order(self) -> list[str]:
        """Return intent patterns in priority order."""
        return [
            "invoice",
            "exception",
            "add_note",
            "mark_reconciled",
            "release_payment",
            "route_to_review",
            "escalate",
            "submit",
            "save",
        ]

    def _find_invoice_row(
        self, elements: list[Any], url: str, intent: str | None = None
    ) -> int | None:
        """Find first invoice row with exceptions in the queue.

        Args:
            elements: List of snapshot elements
            url: Current page URL
            intent: Intent hint (may contain specific invoice ID like "INV-2024-001")
        """
        # Extract specific invoice ID from intent if provided (e.g., "INV-2024-001")
        specific_invoice_id = None
        if intent:
            import re

            match = re.search(
                r"(INV[_-]?\d{4}[_-]?\d{3})", intent.upper().replace("-", "_").replace(" ", "_")
            )
            if match:
                specific_invoice_id = match.group(1).replace("_", "-").upper()

        candidates = []
        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role not in {"link", "button", "row", "cell"}:
                continue

            text = (getattr(el, "text", "") or "").lower()
            href = (getattr(el, "href", "") or "").lower()

            # Look for invoice links or rows with exception indicators
            if "inv" in text or "invoice" in text or "/invoices/" in href:
                # Check for specific invoice ID match (highest priority)
                exact_match = 0
                if specific_invoice_id:
                    text_upper = text.upper()
                    if specific_invoice_id in text_upper or specific_invoice_id.replace(
                        "-", ""
                    ) in text_upper.replace("-", ""):
                        exact_match = -1  # Highest priority

                # Prefer rows with exceptions
                has_exception = "exception" in text or "discrepancy" in text or "mismatch" in text
                in_viewport = bool(getattr(el, "in_viewport", True))
                doc_y = getattr(el, "doc_y", None) or 1e9
                importance = getattr(el, "importance", 0) or 0

                # Higher priority for exact matches, then exceptions
                exception_score = 0 if has_exception else 1
                candidates.append(
                    (exact_match, exception_score, not in_viewport, doc_y, -importance, el.id)
                )

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][5]

    def _find_add_note_element(self, elements: list[Any]) -> int | None:
        """Find add note button or textarea."""
        candidates = []
        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            text = (getattr(el, "text", "") or "").lower()
            placeholder = (getattr(el, "placeholder", "") or "").lower()

            # Look for note-related elements
            if role in {"textarea", "textbox"} and (
                "note" in placeholder or "comment" in placeholder
            ):
                # Prefer textareas for notes
                candidates.append((0, getattr(el, "doc_y", 1e9), el.id))
            elif role == "button" and ("note" in text or "add" in text):
                candidates.append((1, getattr(el, "doc_y", 1e9), el.id))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2]

    def _find_reconcile_button(self, elements: list[Any]) -> int | None:
        """Find mark reconciled button."""
        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role != "button":
                continue
            text = (getattr(el, "text", "") or "").lower()
            if "reconcil" in text or "mark" in text:
                return el.id
        return None

    def _find_release_payment_button(self, elements: list[Any]) -> int | None:
        """Find release payment button."""
        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role != "button":
                continue
            text = (getattr(el, "text", "") or "").lower()
            if "release" in text or "payment" in text or "approve" in text:
                return el.id
        return None

    def _find_route_to_review_button(self, elements: list[Any]) -> int | None:
        """Find route to review button."""
        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role != "button":
                continue
            text = (getattr(el, "text", "") or "").lower()
            if "review" in text or "route" in text or "escalate" in text:
                return el.id
        return None

    def _find_submit_button(self, elements: list[Any]) -> int | None:
        """Find submit/save button."""
        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role != "button":
                continue
            text = (getattr(el, "text", "") or "").lower()
            if "submit" in text or "save" in text or "confirm" in text:
                return el.id
        return None

    def _find_note_textbox(self, elements: list[Any]) -> int | None:
        """Find textbox/textarea for adding notes."""
        candidates = []
        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role not in {"textbox", "textarea", "input"}:
                continue
            text = (getattr(el, "text", "") or "").lower()
            placeholder = (getattr(el, "placeholder", "") or "").lower()

            # Prefer textboxes related to notes
            if (
                "note" in text
                or "note" in placeholder
                or "comment" in text
                or "comment" in placeholder
            ):
                importance = getattr(el, "importance", 0) or 0
                doc_y = getattr(el, "doc_y", 1e9)
                candidates.append((-importance, doc_y, el.id))

        if not candidates:
            # No note-specific textbox, try to find any visible textbox
            return self._find_first_textbox(elements)
        candidates.sort()
        return candidates[0][2]

    def _find_first_textbox(self, elements: list[Any]) -> int | None:
        """Find first visible textbox/textarea."""
        candidates = []
        for el in elements:
            role = (getattr(el, "role", "") or "").lower()
            if role not in {"textbox", "textarea", "input"}:
                continue
            importance = getattr(el, "importance", 0) or 0
            doc_y = getattr(el, "doc_y", 1e9)
            candidates.append((-importance, doc_y, el.id))

        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2]


# ---------------------------------------------------------------------------
# Verification Predicates (Hard Outcomes)
# ---------------------------------------------------------------------------


def get_beat_1_verification() -> list[Predicate]:
    """
    Beat 1: Open invoice, compare fields, add note.

    Verification: We're on the invoice detail page.
    The note addition is verified by the stepwise planner completing successfully.
    """
    return [
        url_contains("/demo/finance/invoices/"),
    ]


def get_beat_2_verification() -> list[Predicate]:
    """
    Beat 2: Mark Reconciled - silent failure detection.

    Verification: Status indicator should show "reconciled" but it won't change.
    This predicate is expected to FAIL because the UI doesn't update (silent failure).

    On LocalLlamaLand, the reconciliation status shows as "needs review" and should
    change to "reconciled" if the action succeeded - but it won't due to silent failure.

    We look for a span element containing "reconciled" text (the status badge).
    After silent failure, this should NOT exist - status stays "needs review".
    """
    return [
        # Look for span with "reconciled" text - the status badge
        # This should NOT be found after the silent failure (status stays "needs review")
        exists("role=span text~'reconciled'"),
    ]


def get_beat_3_verification() -> list[Predicate]:
    """
    Beat 3: Release Payment - risky action blocked by policy.

    This beat is blocked by policy BEFORE execution, so verification
    isn't actually run. We include a simple URL check as a fallback.
    """
    return [
        # Policy blocks this action before it runs, so this is a fallback
        url_contains("/demo/finance/"),
    ]


def get_beat_4_verification() -> list[Predicate]:
    """
    Beat 4: Route To Review - safe fallback action.

    Verification: We're still on the invoice page after routing to review.
    The Route To Review button click is verified by stepwise planner success.
    """
    return [
        url_contains("/demo/finance/invoices/"),
    ]


# ---------------------------------------------------------------------------
# Task Definitions (Soft Plans - LLM generates the steps)
# ---------------------------------------------------------------------------


def get_beat_1_task() -> AutomationTask:
    """
    Beat 1: Open invoice and add a note.

    Task objective given to the planner. The planner decides HOW to accomplish it.
    """
    invoice_id = get_beat_invoice_id(DemoBeat.OPEN_AND_NOTE)
    return AutomationTask(
        task_id="beat-1-open-and-note",
        starting_url=f"https://www.localllamaland.com/demo/finance/invoices/{invoice_id}",
        task=(
            f"Open invoice {invoice_id} in the finance app, compare the invoice amount "
            "with the PO amount, and add a note explaining any discrepancy found."
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
    invoice_id = get_beat_invoice_id(DemoBeat.MARK_RECONCILED)
    return AutomationTask(
        task_id="beat-2-mark-reconciled",
        starting_url=f"https://www.localllamaland.com/demo/finance/invoices/{invoice_id}",
        task=(
            f"Open invoice {invoice_id} in the finance app and click the 'Mark Reconciled' "
            "button to mark this invoice as reconciled. Verify the status indicator updates."
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
    invoice_id = get_beat_invoice_id(DemoBeat.ROUTE_TO_REVIEW)
    return AutomationTask(
        task_id="beat-4-route-to-review",
        starting_url=f"https://www.localllamaland.com/demo/finance/invoices/{invoice_id}",
        task=(
            f"Open invoice {invoice_id} in the finance app and route it to manager review "
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


def get_beat_invoice_id(beat: DemoBeat) -> str:
    """Return the deterministic invoice ID for a demo beat."""
    invoice_map = {
        DemoBeat.OPEN_AND_NOTE: "INV-2024-005",
        DemoBeat.MARK_RECONCILED: "INV-2024-002",
        DemoBeat.RELEASE_PAYMENT: "INV-2024-001",
        DemoBeat.ROUTE_TO_REVIEW: "INV-2024-001",
    }
    return invoice_map[beat]


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
        invoice_id = get_beat_invoice_id(beat)
        auth_result = authorizer.authorize_beat_action(
            beat_name=beat.value,
            action=action,
            invoice_id=invoice_id,
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
        # Reset the browser to the task's declared starting page so each beat
        # runs against the intended invoice/context instead of leaking state.
        await runtime.goto(task.starting_url)

        # Execute the task using stepwise (ReAct-style) planning
        # Plans one step at a time based on current page state
        # SDK now includes stabilization before each planning snapshot
        outcome = await agent.run_stepwise(runtime, task)

        # Verify the expected outcome using hard predicates
        # SDK predicates are functions - use runtime.assert_() which evaluates immediately
        # and returns True/False
        verification_passed = True
        for i, pred in enumerate(verification):
            label = f"verification_{beat.value}_{i}"
            try:
                passed = runtime.assert_(pred, label)
                if not passed:
                    logger.warning(f"Verification predicate {i} failed for {beat.value}")
                    verification_passed = False
                    break
            except Exception as e:
                logger.warning(f"Verification predicate {i} raised exception: {e}")
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
            authorizer = create_demo_authorizer(policy_file, sidecar_url=config.sidecar.url)
            logger.info("Authorization enabled with policy file")
            logger.info("Authorization mode: %s", authorizer.authorization_mode_label)
        except FileNotFoundError as e:
            logger.warning(f"Policy file not found, running without authorization: {e}")
        except Exception as e:
            logger.warning(f"Failed to create authorizer, running without authorization: {e}")

    # Create SDK providers
    planner = create_sdk_provider(config, "planner")
    executor = create_sdk_provider(config, "executor")

    # Create tracer using unified create_tracer() factory
    # - With API key: uploads to Predicate Studio (cloud)
    # - Without API key: saves to local JSONL file
    # The tracer auto-closes on process exit (atexit) as safety net
    logger.info(
        "Using Predicate cloud tracing"
        if config.has_predicate_api_key
        else "Using local file tracing (set PREDICATE_API_KEY for cloud tracing)"
    )
    tracer = create_tracer(
        api_key=config.predicate_api_key if config.has_predicate_api_key else None,
        run_id=run_id,
        api_url=config.predicate_api_url if config.has_predicate_api_key else None,
        goal="Account Payable Demo - Finance Workflow",
        agent_type="planner-executor",
        llm_model=config.get_planner_model(),
        start_url=config.app.finance_queue_url,
    )

    # Create agent config with comprehensive settings
    # Mirrors the approach in sentience-sdk-playground/planner_executor_local2
    agent_config = PlannerExecutorConfig(
        # Snapshot escalation for reliable element capture
        snapshot=SnapshotEscalationConfig(
            enabled=True,
            limit_base=60,
            limit_step=30,
            limit_max=200,
        ),
        # Retry/verification settings
        retry=RetryConfig(
            verify_timeout_s=15.0,
            verify_poll_s=0.5,
            verify_max_attempts=6,
            executor_repair_attempts=3,
            max_replans=2,
        ),
        # LLM settings
        planner_max_tokens=2048,
        planner_temperature=0.0,
        executor_max_tokens=96,
        executor_temperature=0.0,
        # Stabilization
        stabilize_enabled=True,
        stabilize_poll_s=0.35,
        stabilize_max_attempts=6,
        # Pre-step verification
        pre_step_verification=True,
        # Tracing
        trace_screenshots=True,
        # Verbose mode - print plan and executor prompts to stdout for debugging
        verbose=True,
        # Stepwise planning config (ReAct-style)
        stepwise=StepwisePlanningConfig(
            max_steps=30,
            action_history_limit=5,
            include_page_context=True,
        ),
        # Disable modal auto-dismissal - this demo involves intentional form interactions
        # where modals should NOT be automatically dismissed
        modal=ModalDismissalConfig(enabled=False),
    )

    # Custom context formatter that includes ALL elements (not just interactive roles)
    # This is necessary because LocalLlamaLand demo pages may not have proper ARIA roles
    def format_context(snap, goal):
        """Format snapshot for LLM with all elements, not just interactive roles."""
        # Debug: log element count
        element_count = len(snap.elements) if snap.elements else 0
        logger.info(f"[format_context] Snapshot has {element_count} elements, URL: {snap.url}")

        lines = []
        # Sort by importance descending, take top 100 elements
        elements = sorted(snap.elements or [], key=lambda e: e.importance or 0, reverse=True)[:100]

        for el in elements:
            role = el.role or "element"
            # Get text, truncate to 40 chars
            text = (el.text or "").strip()
            text = " ".join(text.split())  # Normalize whitespace
            if len(text) > 40:
                text = text[:37] + "..."

            importance = el.importance or 0
            is_primary = "1" if (el.visual_cues and el.visual_cues.is_primary) else "0"
            doc_yq = int(round((el.doc_y or 0) / 200))

            # Dominant group info
            in_dg = el.in_dominant_group or False
            dg_flag = "1" if in_dg else "0"
            ord_val = el.group_index if in_dg and el.group_index is not None else "-"

            # Href (compressed)
            href = ""
            if el.href:
                # Extract last path segment
                parts = [p for p in el.href.split("/") if p]
                href = parts[-1][:20] if parts else ""

            lines.append(
                f"{el.id}|{role}|{text}|{importance}|{is_primary}|{doc_yq}|{ord_val}|{dg_flag}|{href}"
            )

        header = "ID|role|text|imp|is_primary|docYq|ord|DG|href"
        return f"{header}\n" + "\n".join(lines) if lines else header

    # Create agent with custom heuristics and context formatter
    agent = PlannerExecutorAgent(
        planner=planner,
        executor=executor,
        config=agent_config,
        tracer=tracer,
        context_formatter=format_context,
        intent_heuristics=FinanceHeuristics(),
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

    # Configure SnapshotOptions with show_overlay, API key, and screenshot config
    # Using ScreenshotConfig for explicit format/quality settings (required for Studio)
    snapshot_options = SnapshotOptions(
        limit=60,
        screenshot=ScreenshotConfig(format="jpeg", quality=80),
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

    # Use async context managers for automatic cleanup:
    # - tracer: auto-closes and uploads trace data to Predicate Studio
    # - browser: auto-closes Playwright browser
    async with tracer:
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

        # Collect authorization log (after browser closes, before tracer closes)
        if authorizer is not None:
            result.authorization_log = authorizer.get_authorization_log()

        # Collect token usage
        if result.beats and result.beats[0].outcome:
            token_usage = result.beats[0].outcome.token_usage
            if token_usage:
                result.total_tokens = token_usage.get("total", {}).get("total_tokens", 0)

    # tracer.close() called automatically by async context manager
    logger.info("Tracer closed - trace data uploaded to Predicate Studio")

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
