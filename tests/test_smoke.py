"""Workflow-logic smoke tests for the Account Payable Demo.

These are deterministic smoke tests that verify the workflow's decision logic,
authorization boundaries, and success/failure branching for all demo paths.

NOTE: These tests mock the browser and LLM to ensure stability and speed.
They do NOT test actual visible-state changes in a real browser DOM.
For live browser E2E tests, see the local-llama-land test suite.

What these tests cover:
1. Normal success path logic (Beat 1 & 4) - workflow branching when verification passes
2. Silent failure detection logic (Beat 2) - workflow recognizes verification failure as demo success
3. Denied action path logic (Beat 3) - pre-action authorization blocks execution

What these tests do NOT cover (verification gaps):
- Real DOM state changes or selector matching
- Actual browser automation or page rendering
- LLM response parsing or plan generation
- Network latency, timeouts, or error recovery

Design principles:
- Deterministic tests that don't require a live browser
- Focus on the authorization and verification control flow
- Mock external dependencies (LLM, browser) to ensure stability
- Cover the critical decision points in the workflow logic
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from predicate_contracts import AuthorizationReason

from account_payable_demo.authorization import (
    AuthorizationResult,
    DemoAction,
    DemoPrincipal,
    create_demo_authorizer,
    create_runtime_authorizer,
    get_principal_for_beat,
)
from account_payable_demo.config import DemoConfig
from account_payable_demo.workflow import (
    BeatResult,
    DemoBeat,
    WorkflowResult,
    execute_beat,
    get_beat_1_task,
    get_beat_1_verification,
    get_beat_2_task,
    get_beat_2_verification,
    get_beat_3_task,
    get_beat_3_verification,
    get_beat_4_task,
    get_beat_4_verification,
    get_beat_action,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def demo_authorizer():
    """Create an authorizer using the actual demo policy file."""
    demo_root = Path(__file__).parent.parent
    policy_file = demo_root / "policy.yaml"
    if not policy_file.exists():
        pytest.skip("Demo policy file not found")
    return create_demo_authorizer(policy_file)


@pytest.fixture
def mock_agent():
    """Create a mock PlannerExecutorAgent."""
    agent = MagicMock()
    # Mock the run method to return a successful outcome
    mock_outcome = MagicMock()
    mock_outcome.fallback_used = False
    mock_outcome.error = None
    mock_outcome.total_duration_ms = 1000
    agent.run = AsyncMock(return_value=mock_outcome)
    return agent


@pytest.fixture
def mock_runtime():
    """Create a mock AgentRuntime with verification support."""
    runtime = MagicMock()

    # Mock the context for predicate evaluation (legacy, kept for compatibility)
    mock_ctx = MagicMock()
    mock_ctx.url = "https://www.localllamaland.com/demo/finance/queue"
    mock_ctx.page_content = ""
    runtime._ctx = MagicMock(return_value=mock_ctx)

    # Mock assert_() method for predicate evaluation
    # Default behavior: all predicates pass (True)
    runtime.assert_ = MagicMock(return_value=True)

    return runtime


# ---------------------------------------------------------------------------
# Smoke Test 1: Normal Success Path Logic
# ---------------------------------------------------------------------------


class TestNormalSuccessPathLogic:
    """Workflow-logic smoke tests for the normal success path.

    Tests the workflow's decision logic when beats are authorized and
    verification predicates pass. Uses mocked verification - does NOT
    test actual DOM state changes.

    Covers Beat 1 (Open and Note) and Beat 4 (Route to Review).
    """

    def test_beat_1_authorized_by_policy(self, demo_authorizer):
        """Beat 1: Add note action is authorized."""
        result = demo_authorizer.authorize_beat_action(
            beat_name="open_and_note",
            action=DemoAction.ADD_NOTE,
        )

        assert result.allowed is True, "Beat 1 should be authorized"
        assert result.denied is False
        # Should use invoice-intake principal
        assert get_principal_for_beat("open_and_note") == DemoPrincipal.INVOICE_INTAKE

    def test_beat_4_authorized_by_policy(self, demo_authorizer):
        """Beat 4: Route to review action is authorized."""
        result = demo_authorizer.authorize_beat_action(
            beat_name="route_to_review",
            action=DemoAction.ROUTE_TO_REVIEW,
        )

        assert result.allowed is True, "Beat 4 should be authorized"
        assert result.denied is False
        # Should use resolution principal
        assert get_principal_for_beat("route_to_review") == DemoPrincipal.RESOLUTION

    @pytest.mark.asyncio
    async def test_beat_1_executes_successfully(self, demo_authorizer, mock_agent, mock_runtime):
        """Beat 1: Execute beat and verify success logic."""
        task = get_beat_1_task()
        verification = get_beat_1_verification()

        # Mock runtime.assert_() to return True (verification passes)
        mock_runtime.assert_ = MagicMock(return_value=True)

        result = await execute_beat(
            agent=mock_agent,
            runtime=mock_runtime,
            beat=DemoBeat.OPEN_AND_NOTE,
            task=task,
            verification=verification,
            authorizer=demo_authorizer,
        )

        assert result.beat == DemoBeat.OPEN_AND_NOTE
        assert result.success is True, "Beat 1 should succeed when verification passes"
        assert result.was_policy_blocked is False
        assert result.details.get("verification_passed") is True

    @pytest.mark.asyncio
    async def test_beat_4_executes_successfully(self, demo_authorizer, mock_agent, mock_runtime):
        """Beat 4: Execute beat and verify success logic."""
        task = get_beat_4_task()
        verification = get_beat_4_verification()

        # Mock runtime.assert_() to return True (verification passes)
        mock_runtime.assert_ = MagicMock(return_value=True)

        result = await execute_beat(
            agent=mock_agent,
            runtime=mock_runtime,
            beat=DemoBeat.ROUTE_TO_REVIEW,
            task=task,
            verification=verification,
            authorizer=demo_authorizer,
        )

        assert result.beat == DemoBeat.ROUTE_TO_REVIEW
        assert result.success is True, "Beat 4 should succeed when verification passes"
        assert result.was_policy_blocked is False


# ---------------------------------------------------------------------------
# Smoke Test 2: Silent Failure Detection Logic
# ---------------------------------------------------------------------------


class TestSilentFailureDetectionLogic:
    """Workflow-logic smoke tests for the silent failure detection path.

    Tests the workflow's inverted success logic for Beat 2: the demo
    succeeds when verification FAILS, proving we can detect "click
    worked but state didn't change."

    Uses mocked verification - does NOT test actual DOM state detection.
    Covers Beat 2 (Mark Reconciled).
    """

    def test_beat_2_authorized_by_policy(self, demo_authorizer):
        """Beat 2: Mark reconciled action is authorized."""
        result = demo_authorizer.authorize_beat_action(
            beat_name="mark_reconciled",
            action=DemoAction.MARK_RECONCILED,
        )

        assert result.allowed is True, "Beat 2 action should be authorized"
        # Should use reconciliation principal
        assert get_principal_for_beat("mark_reconciled") == DemoPrincipal.RECONCILIATION

    @pytest.mark.asyncio
    async def test_beat_2_demo_succeeds_when_verification_fails(
        self, demo_authorizer, mock_agent, mock_runtime
    ):
        """Beat 2: Demo succeeds when verification correctly detects failure.

        This is the KEY silent failure test:
        - The agent clicks "Mark Reconciled"
        - The button appears to work (no error)
        - But the state never changes
        - Our verification predicates detect this
        - The demo counts this as SUCCESS (we caught the silent failure)
        """
        task = get_beat_2_task()
        verification = get_beat_2_verification()

        # Mock runtime.assert_() to return False (verification fails - state didn't change)
        mock_runtime.assert_ = MagicMock(return_value=False)

        result = await execute_beat(
            agent=mock_agent,
            runtime=mock_runtime,
            beat=DemoBeat.MARK_RECONCILED,
            task=task,
            verification=verification,
            authorizer=demo_authorizer,
        )

        assert result.beat == DemoBeat.MARK_RECONCILED
        # Demo SUCCEEDS when verification FAILS (we detected the silent failure)
        assert result.success is True, (
            "Beat 2 demo should succeed when verification fails "
            "(proving we detected the silent failure)"
        )
        assert result.was_policy_blocked is False
        assert result.details.get("verification_passed") is False

    @pytest.mark.asyncio
    async def test_beat_2_demo_fails_when_state_actually_changes(
        self, demo_authorizer, mock_agent, mock_runtime
    ):
        """Beat 2: If state actually changes, demo fails (unexpected success)."""
        task = get_beat_2_task()
        verification = get_beat_2_verification()

        # Mock runtime.assert_() to return True (verification passes - state changed unexpectedly!)
        mock_runtime.assert_ = MagicMock(return_value=True)

        result = await execute_beat(
            agent=mock_agent,
            runtime=mock_runtime,
            beat=DemoBeat.MARK_RECONCILED,
            task=task,
            verification=verification,
            authorizer=demo_authorizer,
        )

        # Demo FAILS when verification PASSES (unexpected - state changed)
        assert result.success is False, (
            "Beat 2 demo should fail when verification passes (state changed unexpectedly)"
        )


# ---------------------------------------------------------------------------
# Smoke Test 3: Denied Action Path Logic
# ---------------------------------------------------------------------------


class TestDeniedActionPathLogic:
    """Workflow-logic smoke tests for the denied risky action path.

    Tests the workflow's pre-action authorization blocking and the
    inverted success logic: demo succeeds when policy blocks the action.

    Covers Beat 3 (Release Payment).
    """

    def test_beat_3_denied_by_policy(self, demo_authorizer):
        """Beat 3: Release payment action is denied by policy."""
        result = demo_authorizer.authorize_beat_action(
            beat_name="release_payment",
            action=DemoAction.RELEASE_PAYMENT,
        )

        assert result.denied is True, "Beat 3 should be denied by policy"
        assert result.allowed is False
        assert result.reason == AuthorizationReason.EXPLICIT_DENY
        assert result.violated_rule == "deny-payment-release"

    @pytest.mark.asyncio
    async def test_beat_3_blocked_before_execution(self, demo_authorizer, mock_agent, mock_runtime):
        """Beat 3: Execution is blocked before reaching the browser.

        This is the KEY authorization test:
        - The agent tries to release payment
        - Policy denies before any browser action
        - The demo counts this as SUCCESS (we prevented the risky action)
        """
        task = get_beat_3_task()
        verification = get_beat_3_verification()

        result = await execute_beat(
            agent=mock_agent,
            runtime=mock_runtime,
            beat=DemoBeat.RELEASE_PAYMENT,
            task=task,
            verification=verification,
            authorizer=demo_authorizer,
        )

        assert result.beat == DemoBeat.RELEASE_PAYMENT
        # Demo SUCCEEDS when policy BLOCKS (we prevented risky action)
        assert result.success is True, (
            "Beat 3 demo should succeed when policy blocks (proving authorization works)"
        )
        assert result.was_policy_blocked is True
        assert result.details.get("policy_blocked") is True
        assert result.details.get("violated_rule") == "deny-payment-release"

        # Verify agent.run was NEVER called (blocked before execution)
        mock_agent.run.assert_not_called()

    def test_runtime_authorizer_blocks_payment_release(self, demo_authorizer):
        """Runtime-level authorization blocks payment release clicks."""
        callback = create_runtime_authorizer(demo_authorizer, fail_closed=True)

        class PaymentReleaseRequest:
            action = "browser.click"
            action_spec = type(
                "ActionSpec",
                (),
                {
                    "action": "browser.click",
                    "resource": "https://www.localllamaland.com/demo/finance/invoices/INV-001/release",
                    "intent": "Click Release Payment button",
                },
            )()

        with pytest.raises(RuntimeError, match="pre_action_authority_denied"):
            callback(PaymentReleaseRequest())


# ---------------------------------------------------------------------------
# Integration Smoke Tests
# ---------------------------------------------------------------------------


class TestWorkflowIntegration:
    """Integration smoke tests for the complete workflow logic.

    These tests verify the workflow result aggregation and
    authorization log collection.
    """

    def test_workflow_result_tracks_authorization_log(self, demo_authorizer):
        """WorkflowResult correctly aggregates authorization decisions."""
        # Clear any previous log entries
        demo_authorizer.clear_log()

        # Simulate authorizing all 4 beats
        demo_authorizer.authorize_beat_action("open_and_note", DemoAction.ADD_NOTE)
        demo_authorizer.authorize_beat_action("mark_reconciled", DemoAction.MARK_RECONCILED)
        demo_authorizer.authorize_beat_action("release_payment", DemoAction.RELEASE_PAYMENT)
        demo_authorizer.authorize_beat_action("route_to_review", DemoAction.ROUTE_TO_REVIEW)

        log = demo_authorizer.get_authorization_log()

        # Should have 4 authorization decisions
        assert len(log) == 4

        # 3 allowed, 1 denied
        allowed = demo_authorizer.get_allowed_actions()
        denied = demo_authorizer.get_denied_actions()

        assert len(allowed) == 3, "Should have 3 allowed actions"
        assert len(denied) == 1, "Should have 1 denied action"
        assert denied[0].action == DemoAction.RELEASE_PAYMENT.value

    def test_workflow_result_policy_denials_property(self):
        """WorkflowResult.policy_denials filters correctly."""
        result = WorkflowResult()

        # Add mock authorization results
        allowed_auth = AuthorizationResult(
            allowed=True,
            action="invoice.add_note",
            resource="https://example.com/notes",
            reason=AuthorizationReason.ALLOWED,
        )
        denied_auth = AuthorizationResult(
            allowed=False,
            action="payment.release",
            resource="https://example.com/release",
            reason=AuthorizationReason.EXPLICIT_DENY,
            violated_rule="deny-payment-release",
        )

        result.authorization_log = [allowed_auth, denied_auth]

        assert len(result.policy_denials) == 1
        assert result.policy_denials[0].action == "payment.release"
        assert len(result.policy_allows) == 1
        assert result.policy_allows[0].action == "invoice.add_note"

    def test_beat_result_policy_blocked_property(self):
        """BeatResult.was_policy_blocked correctly identifies blocked beats."""
        # Blocked beat
        blocked_auth = AuthorizationResult(
            allowed=False,
            action="payment.release",
            resource="https://example.com/release",
            reason=AuthorizationReason.EXPLICIT_DENY,
            violated_rule="deny-payment-release",
        )
        blocked_result = BeatResult(
            beat=DemoBeat.RELEASE_PAYMENT,
            success=True,
            authorization=blocked_auth,
        )
        assert blocked_result.was_policy_blocked is True

        # Non-blocked beat
        allowed_auth = AuthorizationResult(
            allowed=True,
            action="invoice.add_note",
            resource="https://example.com/notes",
            reason=AuthorizationReason.ALLOWED,
        )
        allowed_result = BeatResult(
            beat=DemoBeat.OPEN_AND_NOTE,
            success=True,
            authorization=allowed_auth,
        )
        assert allowed_result.was_policy_blocked is False

        # Beat without authorization
        no_auth_result = BeatResult(
            beat=DemoBeat.OPEN_AND_NOTE,
            success=True,
        )
        assert no_auth_result.was_policy_blocked is False


# ---------------------------------------------------------------------------
# Principal Mapping Smoke Tests
# ---------------------------------------------------------------------------


class TestPrincipalMappingSmoke:
    """Smoke tests for beat-to-principal mapping.

    Verifies that each beat uses the correct agent principal
    for role-based authorization.
    """

    def test_all_beats_have_correct_principals(self):
        """All beats map to their expected principals."""
        mappings = [
            ("open_and_note", DemoPrincipal.INVOICE_INTAKE),
            ("mark_reconciled", DemoPrincipal.RECONCILIATION),
            ("release_payment", DemoPrincipal.RESOLUTION),
            ("route_to_review", DemoPrincipal.RESOLUTION),
        ]

        for beat_name, expected_principal in mappings:
            actual = get_principal_for_beat(beat_name)
            assert actual == expected_principal, (
                f"Beat '{beat_name}' should use principal '{expected_principal.value}', "
                f"got '{actual.value}'"
            )

    def test_beat_to_action_mapping(self):
        """All beats map to their expected actions."""
        mappings = [
            (DemoBeat.OPEN_AND_NOTE, DemoAction.ADD_NOTE),
            (DemoBeat.MARK_RECONCILED, DemoAction.MARK_RECONCILED),
            (DemoBeat.RELEASE_PAYMENT, DemoAction.RELEASE_PAYMENT),
            (DemoBeat.ROUTE_TO_REVIEW, DemoAction.ROUTE_TO_REVIEW),
        ]

        for beat, expected_action in mappings:
            actual = get_beat_action(beat)
            assert actual == expected_action, (
                f"Beat '{beat.value}' should map to action '{expected_action.value}', "
                f"got '{actual.value}'"
            )


# ---------------------------------------------------------------------------
# Configuration Smoke Tests
# ---------------------------------------------------------------------------


class TestConfigurationSmoke:
    """Smoke tests for configuration validation."""

    def test_demo_config_has_required_fields(self):
        """DemoConfig has all required fields for demo operation."""
        config = DemoConfig()

        # Required for authorization
        assert hasattr(config, "has_predicate_api_key")

        # Required for browser
        assert hasattr(config, "headless")
        assert hasattr(config, "show_overlay")

        # Required for tracing
        assert hasattr(config, "trace_output_dir")
        assert hasattr(config, "artifact_output_dir")

        # Required for LLM providers
        assert hasattr(config, "get_planner_model")
        assert hasattr(config, "get_executor_model")
        assert hasattr(config, "get_planner_provider")
        assert hasattr(config, "get_executor_provider")

    def test_show_overlay_defaults_to_true(self):
        """show_overlay should default to True for demo visibility."""
        config = DemoConfig()
        assert config.show_overlay is True
