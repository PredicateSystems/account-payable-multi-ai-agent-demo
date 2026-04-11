"""Tests for the authorization module.

These tests verify:
- Authorization request construction
- Policy denial handling
- Allowed action path behavior
- Integration with the demo workflow
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from predicate_contracts import AuthorizationReason

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

# Minimal policy for testing
TEST_POLICY = """
rules:
  # Deny payment release - key demo rule
  - name: deny-payment-release
    effect: deny
    principals:
      - "agent:*"
    actions:
      - "payment.release"
    resources:
      - "*"

  # Allow adding notes
  - name: allow-add-note
    effect: allow
    principals:
      - "agent:resolution"
    actions:
      - "invoice.add_note"
    resources:
      - "https://www.localllamaland.com/demo/finance/*"

  # Allow marking reconciled
  - name: allow-mark-reconciled
    effect: allow
    principals:
      - "agent:resolution"
    actions:
      - "invoice.mark_reconciled"
    resources:
      - "https://www.localllamaland.com/demo/finance/*"

  # Allow routing to review
  - name: allow-route-to-review
    effect: allow
    principals:
      - "agent:resolution"
    actions:
      - "invoice.route_to_review"
    resources:
      - "https://www.localllamaland.com/demo/finance/*"
"""


@pytest.fixture
def policy_file():
    """Create a temporary policy file for testing."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(TEST_POLICY)
        f.flush()
        yield Path(f.name)


@pytest.fixture
def authorizer(policy_file):
    """Create an ActionAuthorizer for testing."""
    return ActionAuthorizer.from_policy_file(policy_file)


class TestAuthorizationRequestConstruction:
    """Tests for building authorization requests."""

    def test_authorize_constructs_valid_request(self, authorizer):
        """Test that authorize() builds a valid ActionRequest."""
        result = authorizer.authorize(
            action=DemoAction.ADD_NOTE,
            resource="https://www.localllamaland.com/demo/finance/invoices/123/notes",
            intent="Add note to invoice 123",
            principal=DemoPrincipal.RESOLUTION,
        )

        assert isinstance(result, AuthorizationResult)
        assert result.action == "invoice.add_note"
        assert "invoices/123/notes" in result.resource

    def test_authorize_uses_default_principal(self, authorizer):
        """Test that authorize() uses the default principal if not specified."""
        result = authorizer.authorize(
            action=DemoAction.ADD_NOTE,
            resource="https://www.localllamaland.com/demo/finance/invoices/123/notes",
            intent="Add note",
        )

        # Should succeed with default principal (resolution)
        assert isinstance(result, AuthorizationResult)

    def test_authorize_beat_action_builds_correct_resource(self, authorizer):
        """Test authorize_beat_action() builds correct resource URLs."""
        result = authorizer.authorize_beat_action(
            beat_name="release_payment",
            action=DemoAction.RELEASE_PAYMENT,
            invoice_id="INV-2024-001",
        )

        assert "/release" in result.resource
        assert "INV-2024-001" in result.resource

    def test_authorize_with_string_action(self, authorizer):
        """Test authorize() accepts string action names."""
        result = authorizer.authorize(
            action="invoice.add_note",
            resource="https://www.localllamaland.com/demo/finance/invoices/123",
            intent="Add note",
        )

        assert result.action == "invoice.add_note"

    def test_authorize_with_string_principal(self, authorizer):
        """Test authorize() accepts string principal names."""
        result = authorizer.authorize(
            action=DemoAction.ADD_NOTE,
            resource="https://www.localllamaland.com/demo/finance/invoices/123",
            intent="Add note",
            principal="agent:resolution",
        )

        assert isinstance(result, AuthorizationResult)


class TestPolicyDenialHandling:
    """Tests for policy denial behavior."""

    def test_payment_release_is_denied(self, authorizer):
        """Test that payment.release action is denied by policy."""
        result = authorizer.authorize(
            action=DemoAction.RELEASE_PAYMENT,
            resource="https://www.localllamaland.com/demo/finance/invoices/123/release",
            intent="Release payment for invoice 123",
        )

        assert result.denied is True
        assert result.allowed is False
        assert result.reason == AuthorizationReason.EXPLICIT_DENY
        assert result.violated_rule == "deny-payment-release"

    def test_denial_is_explicit_deny(self, authorizer):
        """Test that payment release denial is an explicit deny."""
        result = authorizer.authorize_beat_action(
            beat_name="release_payment",
            action=DemoAction.RELEASE_PAYMENT,
        )

        assert result.is_explicit_deny is True

    def test_denied_actions_logged(self, authorizer):
        """Test that denied actions are logged."""
        # Execute a denied action
        authorizer.authorize_beat_action(
            beat_name="release_payment",
            action=DemoAction.RELEASE_PAYMENT,
        )

        denied = authorizer.get_denied_actions()
        assert len(denied) == 1
        assert denied[0].action == "payment.release"


class TestAllowedActionPath:
    """Tests for allowed action behavior."""

    def test_add_note_is_allowed(self, authorizer):
        """Test that invoice.add_note action is allowed."""
        result = authorizer.authorize(
            action=DemoAction.ADD_NOTE,
            resource="https://www.localllamaland.com/demo/finance/invoices/123/notes",
            intent="Add note to invoice",
        )

        assert result.allowed is True
        assert result.denied is False
        assert result.reason == AuthorizationReason.ALLOWED

    def test_mark_reconciled_is_allowed(self, authorizer):
        """Test that invoice.mark_reconciled action is allowed."""
        result = authorizer.authorize(
            action=DemoAction.MARK_RECONCILED,
            resource="https://www.localllamaland.com/demo/finance/invoices/123/reconcile",
            intent="Mark invoice as reconciled",
        )

        assert result.allowed is True

    def test_route_to_review_is_allowed(self, authorizer):
        """Test that invoice.route_to_review action is allowed."""
        result = authorizer.authorize(
            action=DemoAction.ROUTE_TO_REVIEW,
            resource="https://www.localllamaland.com/demo/finance/invoices/123/review",
            intent="Route to manager review",
        )

        assert result.allowed is True

    def test_allowed_actions_logged(self, authorizer):
        """Test that allowed actions are logged."""
        # Execute allowed actions
        authorizer.authorize_beat_action(
            beat_name="add_note",
            action=DemoAction.ADD_NOTE,
        )
        authorizer.authorize_beat_action(
            beat_name="route_to_review",
            action=DemoAction.ROUTE_TO_REVIEW,
        )

        allowed = authorizer.get_allowed_actions()
        assert len(allowed) == 2


class TestAuthorizationResult:
    """Tests for AuthorizationResult dataclass."""

    def test_result_to_log_dict(self, authorizer):
        """Test that AuthorizationResult can be converted to dict for logging."""
        result = authorizer.authorize_beat_action(
            beat_name="release_payment",
            action=DemoAction.RELEASE_PAYMENT,
        )

        log_dict = result.to_log_dict()

        assert "allowed" in log_dict
        assert "action" in log_dict
        assert "resource" in log_dict
        assert "reason" in log_dict
        assert log_dict["allowed"] is False

    def test_denied_property(self):
        """Test the denied property."""
        result = AuthorizationResult(
            allowed=False,
            action="test.action",
            resource="test://resource",
            reason=AuthorizationReason.EXPLICIT_DENY,
            violated_rule="test-rule",
        )

        assert result.denied is True
        assert result.is_explicit_deny is True

    def test_allowed_result_properties(self):
        """Test properties on an allowed result."""
        result = AuthorizationResult(
            allowed=True,
            action="test.action",
            resource="test://resource",
            reason=AuthorizationReason.ALLOWED,
        )

        assert result.denied is False
        assert result.is_explicit_deny is False


class TestFormatDenialMessage:
    """Tests for format_denial_message helper."""

    def test_format_denial_includes_all_fields(self):
        """Test that denial message includes all relevant fields."""
        result = AuthorizationResult(
            allowed=False,
            action="payment.release",
            resource="https://example.com/release",
            reason=AuthorizationReason.EXPLICIT_DENY,
            violated_rule="deny-payment-release",
        )

        message = format_denial_message(result)

        assert "POLICY DENIAL" in message
        assert "payment.release" in message
        assert "deny-payment-release" in message
        assert "explicit_deny" in message

    def test_format_allowed_message(self):
        """Test formatting an allowed result."""
        result = AuthorizationResult(
            allowed=True,
            action="invoice.add_note",
            resource="https://example.com/notes",
            reason=AuthorizationReason.ALLOWED,
        )

        message = format_denial_message(result)

        assert "is allowed" in message


class TestAuthorizerLifecycle:
    """Tests for authorizer creation and lifecycle."""

    def test_create_from_policy_file(self, policy_file):
        """Test creating authorizer from policy file."""
        authorizer = ActionAuthorizer.from_policy_file(policy_file)

        assert authorizer is not None

    def test_create_from_missing_file_raises(self):
        """Test that missing policy file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            ActionAuthorizer.from_policy_file("/nonexistent/policy.yaml")

    def test_sidecar_authorization_is_used_when_reachable(self, policy_file):
        """Use sidecar HTTP authorization when it is available."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "allowed": True,
            "reason": "allowed",
            "mandate_id": "m_sidecar_123",
            "violated_rule": None,
            "missing_labels": [],
        }

        mock_client = MagicMock()
        mock_client.get.return_value.status_code = 200
        mock_client.post.return_value = mock_response

        with patch("account_payable_demo.authorization.httpx.Client", return_value=mock_client):
            authorizer = create_demo_authorizer(
                policy_file=policy_file,
                sidecar_url="http://localhost:8787",
            )
            assert authorizer.authorization_mode_label == "sidecar"
            result = authorizer.authorize(
                action=DemoAction.ADD_NOTE,
                resource="https://www.localllamaland.com/demo/finance/invoices/123/notes",
                intent="Add note to invoice 123",
                principal=DemoPrincipal.RESOLUTION,
            )

        assert result.allowed is True
        assert result.reason == AuthorizationReason.ALLOWED
        mock_client.post.assert_called_once()

    def test_sidecar_unreachable_falls_back_to_local_policy(self, policy_file):
        """Fall back to local policy evaluation when sidecar is unreachable."""
        mock_client = MagicMock()
        mock_client.get.side_effect = httpx.ConnectError("connection refused")

        with patch("account_payable_demo.authorization.httpx.Client", return_value=mock_client):
            authorizer = create_demo_authorizer(
                policy_file=policy_file,
                sidecar_url="http://localhost:8787",
            )
            assert authorizer.authorization_mode_label == "local fallback"
            result = authorizer.authorize(
                action=DemoAction.ADD_NOTE,
                resource="https://www.localllamaland.com/demo/finance/invoices/123/notes",
                intent="Add note to invoice 123",
                principal=DemoPrincipal.RESOLUTION,
            )

        assert result.allowed is True
        assert result.reason == AuthorizationReason.ALLOWED

    def test_clear_log(self, authorizer):
        """Test clearing the authorization log."""
        # Add some entries
        authorizer.authorize_beat_action(
            beat_name="add_note",
            action=DemoAction.ADD_NOTE,
        )

        assert len(authorizer.get_authorization_log()) > 0

        # Clear the log
        authorizer.clear_log()

        assert len(authorizer.get_authorization_log()) == 0


class TestDemoActionEnum:
    """Tests for DemoAction enum."""

    def test_all_demo_actions_defined(self):
        """Test that all expected demo actions are defined."""
        assert DemoAction.NAVIGATE.value == "browser.navigate"
        assert DemoAction.ADD_NOTE.value == "invoice.add_note"
        assert DemoAction.MARK_RECONCILED.value == "invoice.mark_reconciled"
        assert DemoAction.RELEASE_PAYMENT.value == "payment.release"
        assert DemoAction.ROUTE_TO_REVIEW.value == "invoice.route_to_review"


class TestDemoPrincipalEnum:
    """Tests for DemoPrincipal enum."""

    def test_all_demo_principals_defined(self):
        """Test that all expected demo principals are defined."""
        assert DemoPrincipal.ORCHESTRATOR.value == "agent:orchestrator"
        assert DemoPrincipal.RESOLUTION.value == "agent:resolution"
        assert DemoPrincipal.RECONCILIATION.value == "agent:reconciliation"
        assert DemoPrincipal.INVOICE_INTAKE.value == "agent:invoice-intake"


class TestIntegrationWithDemoPolicy:
    """Integration tests using the actual demo policy.yaml."""

    def test_with_demo_policy_file(self):
        """Test authorization with the actual demo policy file."""
        demo_root = Path(__file__).parent.parent
        policy_file = demo_root / "policy.yaml"

        if not policy_file.exists():
            pytest.skip("Demo policy file not found")

        authorizer = create_demo_authorizer(policy_file)

        # Payment release should be denied
        result = authorizer.authorize_beat_action(
            beat_name="release_payment",
            action=DemoAction.RELEASE_PAYMENT,
        )
        assert result.denied is True

        # Route to review should be allowed
        result = authorizer.authorize_beat_action(
            beat_name="route_to_review",
            action=DemoAction.ROUTE_TO_REVIEW,
        )
        assert result.allowed is True

    def test_demo_workflow_authorization_story(self):
        """Test the complete demo authorization story."""
        demo_root = Path(__file__).parent.parent
        policy_file = demo_root / "policy.yaml"

        if not policy_file.exists():
            pytest.skip("Demo policy file not found")

        authorizer = create_demo_authorizer(policy_file)

        # Beat 1: Add note - should be allowed
        beat1 = authorizer.authorize_beat_action(
            beat_name="open_and_note",
            action=DemoAction.ADD_NOTE,
        )
        assert beat1.allowed is True, "Beat 1 (add note) should be allowed"

        # Beat 2: Mark reconciled - should be allowed
        beat2 = authorizer.authorize_beat_action(
            beat_name="mark_reconciled",
            action=DemoAction.MARK_RECONCILED,
        )
        assert beat2.allowed is True, "Beat 2 (mark reconciled) should be allowed"

        # Beat 3: Release payment - should be DENIED (key demo moment)
        beat3 = authorizer.authorize_beat_action(
            beat_name="release_payment",
            action=DemoAction.RELEASE_PAYMENT,
        )
        assert beat3.denied is True, "Beat 3 (release payment) should be DENIED"
        assert beat3.violated_rule == "deny-payment-release"

        # Beat 4: Route to review - should be allowed (safe fallback)
        beat4 = authorizer.authorize_beat_action(
            beat_name="route_to_review",
            action=DemoAction.ROUTE_TO_REVIEW,
        )
        assert beat4.allowed is True, "Beat 4 (route to review) should be allowed"

        # Summary
        denied = authorizer.get_denied_actions()
        allowed = authorizer.get_allowed_actions()

        assert len(denied) == 1, "Should have exactly 1 denied action"
        assert len(allowed) == 3, "Should have exactly 3 allowed actions"
        assert denied[0].action == "payment.release"


class TestPrincipalMapping:
    """Tests for beat-to-principal mapping."""

    def test_get_principal_for_beat(self):
        """Test that each beat maps to the correct principal."""
        # Invoice intake handles opening and noting
        assert get_principal_for_beat("open_and_note") == DemoPrincipal.INVOICE_INTAKE

        # Reconciliation agent handles marking
        assert get_principal_for_beat("mark_reconciled") == DemoPrincipal.RECONCILIATION

        # Resolution agent handles payment release and review
        assert get_principal_for_beat("release_payment") == DemoPrincipal.RESOLUTION
        assert get_principal_for_beat("route_to_review") == DemoPrincipal.RESOLUTION

    def test_unknown_beat_defaults_to_resolution(self):
        """Test that unknown beats default to resolution principal."""
        assert get_principal_for_beat("unknown_beat") == DemoPrincipal.RESOLUTION

    def test_authorize_beat_action_uses_beat_principal(self, authorizer):
        """Test that authorize_beat_action uses beat-specific principals."""
        # This should use INVOICE_INTAKE principal
        result = authorizer.authorize_beat_action(
            beat_name="open_and_note",
            action=DemoAction.ADD_NOTE,
        )
        # The result should be logged with the correct principal
        assert isinstance(result, AuthorizationResult)


class TestRuntimeAuthorizer:
    """Tests for the runtime authorizer callback."""

    def test_create_runtime_authorizer(self, authorizer):
        """Test creating a runtime authorizer callback."""
        callback = create_runtime_authorizer(authorizer)

        assert isinstance(callback, RuntimeAuthorizerCallback)
        assert callback._authorizer is authorizer
        assert callback._fail_closed is True

    def test_runtime_authorizer_allows_safe_actions(self, authorizer):
        """Test that runtime authorizer allows safe browser actions."""
        callback = create_runtime_authorizer(authorizer, fail_closed=False)

        # Create a mock request for a safe action using the correct demo URL
        class MockRequest:
            action = "browser.click"
            action_spec = type(
                "ActionSpec",
                (),
                {
                    "action": "browser.click",
                    "resource": "https://www.localllamaland.com/demo/finance/invoices/INV-001/notes",
                    "intent": "Add note",
                },
            )()

        result = callback(MockRequest())
        assert result.allowed is True

    def test_runtime_authorizer_denies_payment_release(self, authorizer):
        """Test that runtime authorizer denies payment release clicks."""
        callback = create_runtime_authorizer(authorizer, fail_closed=False)

        # Create a mock request for a payment release action
        class MockRequest:
            action = "browser.click"
            action_spec = type(
                "ActionSpec",
                (),
                {
                    "action": "browser.click",
                    "resource": "https://example.com/release",
                    "intent": "Release payment",
                },
            )()

        result = callback(MockRequest())
        assert result.allowed is False

    def test_runtime_authorizer_raises_on_denial_fail_closed(self, authorizer):
        """Test that runtime authorizer raises exception when fail_closed=True."""
        callback = create_runtime_authorizer(authorizer, fail_closed=True)

        class MockRequest:
            action = "browser.click"
            action_spec = type(
                "ActionSpec",
                (),
                {
                    "action": "browser.click",
                    "resource": "https://example.com/release",
                    "intent": "Release payment",
                },
            )()

        with pytest.raises(RuntimeError, match="pre_action_authority_denied"):
            callback(MockRequest())

    def test_runtime_authorizer_maps_browser_actions(self, authorizer):
        """Test that browser actions are mapped to demo actions based on URL."""
        callback = create_runtime_authorizer(authorizer, fail_closed=False)

        # Test reconcile mapping using correct demo URL
        class ReconcileRequest:
            action = "browser.click"
            action_spec = type(
                "ActionSpec",
                (),
                {
                    "action": "browser.click",
                    "resource": "https://www.localllamaland.com/demo/finance/invoices/INV-001/reconcile",
                    "intent": "Mark reconciled",
                },
            )()

        result = callback(ReconcileRequest())
        assert result.allowed is True  # reconcile is allowed

        # Test review mapping using correct demo URL
        class ReviewRequest:
            action = "browser.click"
            action_spec = type(
                "ActionSpec",
                (),
                {
                    "action": "browser.click",
                    "resource": "https://www.localllamaland.com/demo/finance/invoices/INV-001/review",
                    "intent": "Route to review",
                },
            )()

        result = callback(ReviewRequest())
        assert result.allowed is True  # review is allowed


class TestRuntimeAuthorizationEnforcement:
    """Tests verifying runtime-level authorization enforcement.

    These tests ensure the authorization callback is properly integrated
    at the action execution level, not just at beat-level gating.
    """

    def test_runtime_callback_interface_compatible(self, authorizer):
        """Test that the callback has the interface RuntimeAgent expects."""
        # Use fail_closed=False to test the interface without raising on denial
        callback = create_runtime_authorizer(authorizer, fail_closed=False)

        # RuntimeAgent expects a callable that takes a request and returns
        # an object with .allowed and optionally .reason attributes
        assert callable(callback)

        # Create a minimal request using allowed demo URL
        class MinimalRequest:
            action = "browser.navigate"
            action_spec = type(
                "ActionSpec",
                (),
                {
                    "action": "browser.navigate",
                    "resource": "https://www.localllamaland.com/demo/finance/queue",
                    "intent": "Navigate to queue",
                },
            )()

        # Should not raise
        result = callback(MinimalRequest())
        assert hasattr(result, "allowed")
        assert hasattr(result, "reason")

    def test_authorization_logged_for_runtime_actions(self, authorizer):
        """Test that runtime authorization decisions are logged."""
        callback = create_runtime_authorizer(authorizer, fail_closed=False)

        # Clear the log
        authorizer.clear_log()

        class TestRequest:
            action = "browser.click"
            action_spec = type(
                "ActionSpec",
                (),
                {
                    "action": "browser.click",
                    "resource": "https://example.com/test",
                    "intent": "Test action",
                },
            )()

        callback(TestRequest())

        # Check that the action was logged
        log = authorizer.get_authorization_log()
        assert len(log) == 1
        assert log[0].action == "browser.click"

    def test_payment_release_blocked_at_runtime_level(self, authorizer):
        """Test that payment release is blocked even when detected at runtime.

        This simulates the case where the runtime proposes a click on a
        'release payment' button - the authorization should block it.
        """
        callback = create_runtime_authorizer(authorizer, fail_closed=True)

        # Simulate runtime action request
        class RuntimeActionRequest:
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
            callback(RuntimeActionRequest())

        # Verify the denial was logged
        denied = authorizer.get_denied_actions()
        assert len(denied) >= 1
        assert any(d.action == DemoAction.RELEASE_PAYMENT.value for d in denied)
