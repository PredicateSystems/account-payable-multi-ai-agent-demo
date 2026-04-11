"""Authorization module for Account Payable Demo.

This module provides pre-action authorization using predicate-authority.
It enforces policy boundaries on agent actions before execution.

Key concepts:
- ActionAuthorizer: Main class for authorizing agent actions
- DemoAction: Enum of actions used in the demo
- AuthorizationResult: Result of an authorization check

The demo uses a local policy file (policy.yaml) with embedded authorization.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import httpx
from predicate_authority import AuthorityClient, LocalAuthorizationContext
from predicate_contracts import (
    ActionRequest,
    ActionSpec,
    AuthorizationDecision,
    AuthorizationReason,
    PrincipalRef,
    StateEvidence,
    VerificationEvidence,
    VerificationSignal,
    VerificationStatus,
)

logger = logging.getLogger(__name__)

# Default signing key for demo (in production, use secure key management)
DEMO_SIGNING_KEY = "demo-signing-key-for-development-only"


class DemoAction(str, Enum):
    """Actions used in the Account Payable Demo.

    These map to policy actions in policy.yaml.
    """

    # Navigation actions
    NAVIGATE = "browser.navigate"
    READ = "browser.read"

    # Interaction actions
    CLICK = "browser.click"
    TYPE = "browser.type"
    SUBMIT = "browser.submit"

    # Business actions
    ADD_NOTE = "invoice.add_note"
    MARK_RECONCILED = "invoice.mark_reconciled"
    RELEASE_PAYMENT = "payment.release"
    ROUTE_TO_REVIEW = "invoice.route_to_review"


class DemoPrincipal(str, Enum):
    """Agent principals used in the demo."""

    ORCHESTRATOR = "agent:orchestrator"
    INVOICE_INTAKE = "agent:invoice-intake"
    RECONCILIATION = "agent:reconciliation"
    RESOLUTION = "agent:resolution"


# Beat to principal mapping for role-specific authorization
BEAT_PRINCIPAL_MAP: dict[str, DemoPrincipal] = {
    "open_and_note": DemoPrincipal.INVOICE_INTAKE,  # Invoice intake handles opening and noting
    "mark_reconciled": DemoPrincipal.RECONCILIATION,  # Reconciliation agent handles marking
    "release_payment": DemoPrincipal.RESOLUTION,  # Resolution agent attempts payment release
    "route_to_review": DemoPrincipal.RESOLUTION,  # Resolution agent handles escalation
}


def get_principal_for_beat(beat_name: str) -> DemoPrincipal:
    """Get the appropriate principal for a demo beat.

    Args:
        beat_name: Name of the demo beat

    Returns:
        The principal that should execute this beat
    """
    return BEAT_PRINCIPAL_MAP.get(beat_name, DemoPrincipal.RESOLUTION)


@dataclass(frozen=True)
class AuthorizationResult:
    """Result of an authorization check."""

    allowed: bool
    action: str
    resource: str
    reason: AuthorizationReason
    violated_rule: Optional[str] = None
    missing_labels: tuple[str, ...] = field(default_factory=tuple)
    decision: Optional[AuthorizationDecision] = None

    @property
    def denied(self) -> bool:
        """Check if the action was denied."""
        return not self.allowed

    @property
    def is_explicit_deny(self) -> bool:
        """Check if this was an explicit policy denial."""
        return self.reason == AuthorizationReason.EXPLICIT_DENY

    def to_log_dict(self) -> dict[str, Any]:
        """Convert to a dictionary for logging."""
        return {
            "allowed": self.allowed,
            "action": self.action,
            "resource": self.resource,
            "reason": self.reason.value,
            "violated_rule": self.violated_rule,
            "missing_labels": list(self.missing_labels),
        }


class ActionAuthorizer:
    """Pre-action authorizer using predicate-authority.

    This class wraps the AuthorityClient and provides a simplified interface
    for authorizing actions in the demo workflow.

    Example:
        authorizer = ActionAuthorizer.from_policy_file("policy.yaml")
        result = authorizer.authorize(
            principal=DemoPrincipal.RESOLUTION,
            action=DemoAction.RELEASE_PAYMENT,
            resource="https://www.localllamaland.com/demo/finance/invoices/123/release",
            intent="Release payment for invoice 123",
        )
        if result.denied:
            logger.warning(f"Action denied: {result.violated_rule}")
    """

    def __init__(
        self,
        authority_context: LocalAuthorizationContext,
        default_principal: DemoPrincipal = DemoPrincipal.RESOLUTION,
        sidecar_url: str | None = None,
        sidecar_timeout_s: float = 2.0,
    ) -> None:
        """Initialize the authorizer.

        Args:
            authority_context: The local authorization context
            default_principal: Default principal to use if not specified
            sidecar_url: Optional sidecar base URL for HTTP authorization
            sidecar_timeout_s: Sidecar request timeout in seconds
        """
        self._context = authority_context
        self._client = authority_context.client
        self._default_principal = default_principal
        self._authorization_log: list[AuthorizationResult] = []
        self._sidecar_url = sidecar_url.rstrip("/") if sidecar_url else None
        self._sidecar_timeout_s = sidecar_timeout_s
        self._authorization_mode_label = self._detect_authorization_mode()

    @property
    def authorization_mode_label(self) -> str:
        """Return the active authorization mode for logging/UI."""
        return self._authorization_mode_label

    @classmethod
    def from_policy_file(
        cls,
        policy_file: str | Path,
        signing_key: str = DEMO_SIGNING_KEY,
        ttl_seconds: int = 300,
        default_principal: DemoPrincipal = DemoPrincipal.RESOLUTION,
        sidecar_url: str | None = None,
        sidecar_timeout_s: float = 2.0,
    ) -> ActionAuthorizer:
        """Create an authorizer from a policy file.

        Args:
            policy_file: Path to the YAML policy file
            signing_key: Secret key for mandate signing
            ttl_seconds: Time-to-live for mandates
            default_principal: Default principal to use
            sidecar_url: Optional sidecar base URL for HTTP authorization
            sidecar_timeout_s: Sidecar request timeout in seconds

        Returns:
            ActionAuthorizer instance
        """
        policy_path = Path(policy_file)
        if not policy_path.exists():
            raise FileNotFoundError(f"Policy file not found: {policy_path}")

        context = AuthorityClient.from_policy_file(
            policy_file=str(policy_path),
            secret_key=signing_key,
            ttl_seconds=ttl_seconds,
        )
        return cls(
            authority_context=context,
            default_principal=default_principal,
            sidecar_url=sidecar_url,
            sidecar_timeout_s=sidecar_timeout_s,
        )

    def authorize(
        self,
        action: DemoAction | str,
        resource: str,
        intent: str,
        principal: DemoPrincipal | str | None = None,
        state_hash: str | None = None,
        verification_labels: list[str] | None = None,
    ) -> AuthorizationResult:
        """Authorize an action before execution.

        Args:
            action: The action to authorize
            resource: The resource being acted upon
            intent: Human-readable description of the intent
            principal: The principal performing the action (defaults to resolution agent)
            state_hash: Hash of the current state (auto-generated if not provided)
            verification_labels: Labels from pre-action verification predicates

        Returns:
            AuthorizationResult indicating whether the action is allowed
        """
        # Normalize inputs
        action_str = action.value if isinstance(action, DemoAction) else action
        principal_str = (
            principal.value
            if isinstance(principal, DemoPrincipal)
            else (principal or self._default_principal.value)
        )

        # Generate state hash if not provided
        if state_hash is None:
            state_hash = hashlib.sha256(f"{action_str}:{resource}:{intent}".encode()).hexdigest()[
                :16
            ]

        # Build verification signals from labels
        signals: tuple[VerificationSignal, ...] = ()
        if verification_labels:
            signals = tuple(
                VerificationSignal(
                    label=label,
                    status=VerificationStatus.PASSED,
                    required=False,
                )
                for label in verification_labels
            )

        # Build the action request
        request = ActionRequest(
            principal=PrincipalRef(principal_id=principal_str),
            action_spec=ActionSpec(
                action=action_str,
                resource=resource,
                intent=intent,
            ),
            state_evidence=StateEvidence(
                source="account-payable-demo",
                state_hash=state_hash,
            ),
            verification_evidence=VerificationEvidence(signals=signals),
        )

        # Get authorization decision, preferring the sidecar when configured.
        decision = self._authorize_request(request)

        # Build result
        result = AuthorizationResult(
            allowed=decision.allowed,
            action=action_str,
            resource=resource,
            reason=decision.reason,
            violated_rule=decision.violated_rule,
            missing_labels=decision.missing_labels,
            decision=decision,
        )

        # Log the authorization
        self._authorization_log.append(result)
        self._log_authorization(result)

        return result

    def _authorize_request(self, request: ActionRequest) -> AuthorizationDecision:
        """Authorize via sidecar if configured, else use local policy evaluation."""
        if self._sidecar_url:
            try:
                decision = self._authorize_via_sidecar(request)
                self._authorization_mode_label = "sidecar"
                return decision
            except httpx.HTTPError as exc:
                logger.warning(
                    "Sidecar unreachable at %s; falling back to local policy evaluation: %s",
                    self._sidecar_url,
                    exc,
                )
                self._authorization_mode_label = "local fallback"

        return self._client.authorize(request)

    def _authorize_via_sidecar(self, request: ActionRequest) -> AuthorizationDecision:
        """Call the sidecar /v1/authorize endpoint using the simplified wire format."""
        payload = {
            "principal": request.principal.principal_id,
            "action": request.action_spec.action,
            "resource": request.action_spec.resource,
            "intent_hash": request.state_evidence.state_hash,
            "labels": [
                signal.label
                for signal in request.verification_evidence.signals
                if signal.status == VerificationStatus.PASSED
            ],
        }

        client = httpx.Client(timeout=self._sidecar_timeout_s)
        try:
            response = client.post(f"{self._sidecar_url}/v1/authorize", json=payload)
        finally:
            client.close()

        if response.status_code not in (200, 403):
            response.raise_for_status()

        body = response.json()
        allowed = bool(body.get("allowed", False))
        reason = self._parse_sidecar_reason(body.get("reason", ""), allowed)

        return AuthorizationDecision(
            allowed=allowed,
            reason=reason,
            mandate=None,
            violated_rule=body.get("violated_rule"),
            missing_labels=tuple(body.get("missing_labels", [])),
        )

    def _detect_authorization_mode(self) -> str:
        """Determine whether startup should prefer sidecar or local fallback."""
        if not self._sidecar_url:
            return "local fallback"

        client = httpx.Client(timeout=self._sidecar_timeout_s)
        try:
            response = client.get(f"{self._sidecar_url}/health")
            if response.status_code == 200:
                return "sidecar"
        except httpx.HTTPError:
            pass
        finally:
            client.close()

        return "local fallback"

    @staticmethod
    def _parse_sidecar_reason(raw_reason: str, allowed: bool) -> AuthorizationReason:
        """Map sidecar reason strings to predicate-contracts AuthorizationReason."""
        normalized = (raw_reason or "").strip().lower()
        if normalized.startswith(AuthorizationReason.ALLOWED.value):
            return AuthorizationReason.ALLOWED
        if normalized.startswith(AuthorizationReason.EXPLICIT_DENY.value):
            return AuthorizationReason.EXPLICIT_DENY
        if normalized.startswith(AuthorizationReason.NO_MATCHING_POLICY.value):
            return AuthorizationReason.NO_MATCHING_POLICY
        if normalized.startswith("missing_labels"):
            return AuthorizationReason.MISSING_REQUIRED_VERIFICATION

        return AuthorizationReason.ALLOWED if allowed else AuthorizationReason.NO_MATCHING_POLICY

    def authorize_beat_action(
        self,
        beat_name: str,
        action: DemoAction,
        invoice_id: str = "INV-2024-001",
        base_url: str = "https://www.localllamaland.com",
        principal: DemoPrincipal | str | None = None,
    ) -> AuthorizationResult:
        """Convenience method to authorize beat-specific actions.

        Args:
            beat_name: Name of the demo beat
            action: The action to authorize
            invoice_id: Invoice identifier
            base_url: Base URL of the demo site
            principal: Principal to use (defaults to beat-specific principal)

        Returns:
            AuthorizationResult
        """
        # Use beat-specific principal if not specified
        if principal is None:
            principal = get_principal_for_beat(beat_name)

        # Build resource URL based on action
        if action == DemoAction.RELEASE_PAYMENT:
            resource = f"{base_url}/demo/finance/invoices/{invoice_id}/release"
            intent = f"Release payment for invoice {invoice_id}"
        elif action == DemoAction.MARK_RECONCILED:
            resource = f"{base_url}/demo/finance/invoices/{invoice_id}/reconcile"
            intent = f"Mark invoice {invoice_id} as reconciled"
        elif action == DemoAction.ROUTE_TO_REVIEW:
            resource = f"{base_url}/demo/finance/invoices/{invoice_id}/review"
            intent = f"Route invoice {invoice_id} to manager review"
        elif action == DemoAction.ADD_NOTE:
            resource = f"{base_url}/demo/finance/invoices/{invoice_id}/notes"
            intent = f"Add note to invoice {invoice_id}"
        else:
            resource = f"{base_url}/demo/finance/invoices/{invoice_id}"
            intent = f"Access invoice {invoice_id}"

        principal_str = principal.value if isinstance(principal, DemoPrincipal) else principal
        logger.info(
            "[%s] Authorizing action: %s as %s on %s",
            beat_name,
            action.value,
            principal_str,
            resource,
        )

        return self.authorize(
            action=action,
            resource=resource,
            intent=intent,
            principal=principal,
        )

    def get_authorization_log(self) -> list[AuthorizationResult]:
        """Get the log of all authorization decisions."""
        return list(self._authorization_log)

    def get_denied_actions(self) -> list[AuthorizationResult]:
        """Get all denied actions from the log."""
        return [r for r in self._authorization_log if r.denied]

    def get_allowed_actions(self) -> list[AuthorizationResult]:
        """Get all allowed actions from the log."""
        return [r for r in self._authorization_log if r.allowed]

    def clear_log(self) -> None:
        """Clear the authorization log."""
        self._authorization_log.clear()

    def _log_authorization(self, result: AuthorizationResult) -> None:
        """Log an authorization decision."""
        if result.allowed:
            logger.info("AUTHORIZED: %s on %s", result.action, result.resource)
        else:
            logger.warning(
                "DENIED: %s on %s (reason: %s, rule: %s)",
                result.action,
                result.resource,
                result.reason.value,
                result.violated_rule,
            )


def create_demo_authorizer(
    policy_file: str | Path | None = None,
    sidecar_url: str | None = None,
) -> ActionAuthorizer:
    """Create an authorizer for the demo.

    Args:
        policy_file: Path to policy file (defaults to policy.yaml in demo root)
        sidecar_url: Optional sidecar base URL for HTTP authorization first

    Returns:
        ActionAuthorizer instance
    """
    if policy_file is None:
        # Default to policy.yaml in the demo root
        demo_root = Path(__file__).parent.parent
        policy_file = demo_root / "policy.yaml"

    return ActionAuthorizer.from_policy_file(policy_file, sidecar_url=sidecar_url)


def format_denial_message(result: AuthorizationResult) -> str:
    """Format a human-readable denial message.

    Args:
        result: The authorization result

    Returns:
        Formatted denial message
    """
    if result.allowed:
        return f"Action {result.action} is allowed."

    lines = [
        "=" * 60,
        "POLICY DENIAL",
        "=" * 60,
        f"Action:        {result.action}",
        f"Resource:      {result.resource}",
        f"Reason:        {result.reason.value}",
    ]

    if result.violated_rule:
        lines.append(f"Violated Rule: {result.violated_rule}")

    if result.missing_labels:
        lines.append(f"Missing Labels: {', '.join(result.missing_labels)}")

    lines.append("=" * 60)

    return "\n".join(lines)


class RuntimeAuthorizerCallback:
    """Pre-action authorizer callback for RuntimeAgent.

    This class wraps an ActionAuthorizer and provides the callback interface
    expected by RuntimeAgent.pre_action_authorizer.
    """

    def __init__(
        self,
        authorizer: ActionAuthorizer,
        principal: DemoPrincipal | str = DemoPrincipal.RESOLUTION,
        fail_closed: bool = True,
    ) -> None:
        """Initialize the callback.

        Args:
            authorizer: The ActionAuthorizer to use
            principal: Principal identity for authorization
            fail_closed: If True, raise exception on denial; if False, just log
        """
        self._authorizer = authorizer
        self._principal = principal
        self._fail_closed = fail_closed

    def __call__(self, request: Any) -> Any:
        """Authorize a runtime action request.

        Args:
            request: ActionRequest from the runtime

        Returns:
            Authorization decision

        Raises:
            RuntimeError: If action is denied and fail_closed is True
        """
        # Extract fields from the request
        action = getattr(request, "action", None)
        if hasattr(request, "action_spec"):
            action_spec = request.action_spec
            action = getattr(action_spec, "action", action)
            resource = getattr(action_spec, "resource", "")
            intent = getattr(action_spec, "intent", "")
        else:
            resource = getattr(request, "resource", "")
            intent = getattr(request, "intent", str(request))

        # Map browser actions to demo actions for policy matching
        action_str = str(action) if action else "browser.unknown"
        demo_action = self._map_browser_action_to_demo_action(action_str, resource)

        # Perform authorization
        result = self._authorizer.authorize(
            action=demo_action,
            resource=resource,
            intent=intent,
            principal=self._principal,
        )

        # Handle denial
        if result.denied and self._fail_closed:
            raise RuntimeError(
                f"pre_action_authority_denied: {result.reason.value} (rule: {result.violated_rule})"
            )

        # Return a decision-like object
        return _RuntimeDecision(
            allowed=result.allowed,
            reason=result.reason.value if result.reason else None,
        )

    def _map_browser_action_to_demo_action(self, action: str, resource: str) -> DemoAction | str:
        """Map a browser action to a demo-specific action based on context.

        Args:
            action: The browser action (e.g., "browser.click")
            resource: The resource URL

        Returns:
            The appropriate DemoAction or the original action string
        """
        resource_lower = resource.lower()

        # Check for release payment indicators
        if "release" in resource_lower or "payment" in resource_lower:
            if action == "browser.click":
                return DemoAction.RELEASE_PAYMENT

        # Check for reconcile indicators
        if "reconcile" in resource_lower:
            if action == "browser.click":
                return DemoAction.MARK_RECONCILED

        # Check for review indicators
        if "review" in resource_lower or "escalate" in resource_lower:
            if action == "browser.click":
                return DemoAction.ROUTE_TO_REVIEW

        # Check for notes indicators
        if "note" in resource_lower:
            return DemoAction.ADD_NOTE

        # Default: return original browser action
        return action


class _RuntimeDecision:
    """Simple decision object for RuntimeAgent compatibility."""

    def __init__(self, allowed: bool, reason: str | None = None):
        self.allowed = allowed
        self.reason = reason


def create_runtime_authorizer(
    authorizer: ActionAuthorizer,
    principal: DemoPrincipal | str = DemoPrincipal.RESOLUTION,
    fail_closed: bool = True,
) -> RuntimeAuthorizerCallback:
    """Create a pre-action authorizer callback for RuntimeAgent.

    This function creates a callback that can be passed to RuntimeAgent's
    pre_action_authorizer parameter to enforce policy on every browser action.

    Args:
        authorizer: The ActionAuthorizer to use
        principal: Principal identity for authorization
        fail_closed: If True, raise exception on denial

    Returns:
        Callable for use with RuntimeAgent.pre_action_authorizer

    Example:
        authorizer = create_demo_authorizer()
        runtime_callback = create_runtime_authorizer(authorizer)
        runtime = RuntimeAgent(
            runtime=agent_runtime,
            executor=executor,
            pre_action_authorizer=runtime_callback,
        )
    """
    return RuntimeAuthorizerCallback(
        authorizer=authorizer,
        principal=principal,
        fail_closed=fail_closed,
    )
