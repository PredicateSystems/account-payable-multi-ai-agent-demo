# Account Payable Demo Workflow

This document describes the 4-beat demo workflow using the "soft plans, hard predicates" design.

## Design Philosophy

**Soft Plans, Hard Predicates**:
- **Tasks** define WHAT to accomplish (objectives) - the planner generates the HOW
- **Verification Predicates** define SUCCESS/FAILURE criteria - deterministic hard outcomes
- **Policy Boundaries** constrain allowed/forbidden actions

This keeps the demo bounded and reliable without collapsing it into a hand-scripted flow.

## Browser Target

- **Base URL**: `https://www.localllamaland.com`
- **Finance Queue URL**: `https://www.localllamaland.com/demo/finance/queue`

## Demo Beats Overview

| Beat | Name | Purpose | Expected Outcome |
|------|------|---------|------------------|
| 1 | Open and Note | Standard workflow execution | SUCCESS - note added |
| 2 | Mark Reconciled | Silent failure detection | VERIFICATION_FAILED (status doesn't change) |
| 3 | Release Payment | Policy violation detection | BLOCKED by policy |
| 4 | Route To Review | Safe fallback action | SUCCESS - review requested |

## Beat 1: Open Invoice and Add Note

**Objective**: Navigate to the finance queue, open an invoice, compare fields, and add a note.

**Task** (soft plan - planner generates steps):
```python
AutomationTask(
    task_id="beat-1-open-and-note",
    task="Navigate to the finance queue, select the first invoice with exceptions,
          open its detail view, compare the invoice amount with the PO amount,
          and add a note explaining any discrepancy found.",
    goal={"action": "add_note", "verify": "note_visible"},
    category=TaskCategory.FORM_FILL,
    max_steps=10,
)
```

**Verification** (hard predicates):
```python
[
    url_contains("/demo/finance/invoices/"),
    exists("[data-testid='invoice-notes'], .invoice-notes, .notes-section"),
]
```

## Beat 2: Mark Reconciled (Silent Failure)

**Objective**: Click "Mark Reconciled" and verify the status changes.

**Key Demo Moment**: "The agent clicked the button, but the state never changed."

**Task** (soft plan):
```python
AutomationTask(
    task_id="beat-2-mark-reconciled",
    task="Navigate to the invoice detail view and click the 'Mark Reconciled' button
          to mark this invoice as reconciled. Verify the status indicator updates.",
    goal={"action": "mark_reconciled", "verify": "status_changed"},
    category=TaskCategory.FORM_FILL,
    max_steps=8,
)
```

**Verification** (hard predicates - expected to FAIL):
```python
[
    exists("[data-status='reconciled'], .status-reconciled, .reconciled-badge"),
]
```

**Expected Behavior**: The UI shows the click happening, but the status indicator doesn't change. The verification predicate correctly detects this silent failure.

## Beat 3: Release Payment (Policy Blocked)

**Objective**: Attempt to release payment on an invoice.

**Task** (soft plan):
```python
AutomationTask(
    task_id="beat-3-release-payment",
    task="Navigate to the invoice detail view and attempt to release payment
          by clicking the 'Release Payment' or 'Approve Payment' button.",
    goal={"action": "release_payment"},
    category=TaskCategory.TRANSACTION,  # High-risk category
    max_steps=8,
)
```

**Verification** (hard predicates - handles either outcome):
```python
[
    any_of(
        exists(".payment-released, [data-testid='payment-success']"),
        exists(".policy-denied, .action-blocked, [data-testid='policy-block']"),
    ),
]
```

**Expected Behavior**: The policy blocks this risky action because the invoice hasn't been properly reviewed.

## Beat 4: Route To Review (Safe Fallback)

**Objective**: After the risky action is blocked, route the invoice to manager review.

**Task** (soft plan):
```python
AutomationTask(
    task_id="beat-4-route-to-review",
    task="Navigate to the invoice detail view and route this invoice to manager review
          by clicking 'Route to Review', 'Request Review', or 'Escalate' button.",
    goal={"action": "route_to_review", "verify": "review_requested"},
    category=TaskCategory.FORM_FILL,
    max_steps=8,
)
```

**Verification** (hard predicates):
```python
[
    any_of(
        exists("[data-status='review'], .status-review, .pending-review"),
        exists(".review-requested, [data-testid='review-success']"),
        url_contains("/review"),
    ),
]
```

## SDK Integration

The workflow uses the `predicate-runtime` SDK (version 1.2.0+) with:

- `PlannerExecutorAgent` - Two-tier agent with Planner and Executor LLMs
- `AutomationTask` - Task definition given to planner (soft plan)
- `Predicate` - Verification predicates for outcome checking (hard outcomes)
- `Tracer` - Tracing with `JsonlTraceSink`

### Provider Configuration

| Provider | Config Key | Use Case |
|----------|------------|----------|
| OpenAI | `openai` | Cloud - GPT-4o, GPT-4o-mini |
| Anthropic | `anthropic` | Cloud - Claude 3 |
| DeepInfra | `deepinfra` | Cloud - Llama, Mistral |
| Ollama | `ollama` | Local - Qwen, Llama |

### Example Usage

```python
from account_payable_demo import (
    DemoConfig,
    load_config,
    run_demo_workflow,
    print_workflow_result,
)

# Load config
config = load_config()

# Run workflow
result = await run_demo_workflow(config, headless=True)

# Print results
print_workflow_result(result)
```

## Verification Predicates

### URL Predicates

| Predicate | Arguments | Description |
|-----------|-----------|-------------|
| `url_contains` | `substring: str` | Verifies URL contains substring |

### Element Predicates

| Predicate | Arguments | Description |
|-----------|-----------|-------------|
| `exists` | `selector: str` | Element matching selector is present |
| `not_exists` | `selector: str` | Element matching selector is absent |
| `element_count` | `selector: str, min_count: int, max_count: int` | Element count within range |

### Combinators

| Predicate | Arguments | Description |
|-----------|-----------|-------------|
| `all_of` | `*predicates` | All predicates must pass |
| `any_of` | `*predicates` | At least one predicate must pass |

## Authorization Architecture

The demo implements two authorization layers:

### Beat-Level Authorization (Currently Active)

Before each beat executes, `authorize_beat_action()` checks if the action is allowed:

```python
auth_result = authorizer.authorize_beat_action(
    beat_name=beat.value,
    action=action,
    principal=beat_principal,
)
if auth_result.denied:
    # Block execution before it starts
    return BeatResult(success=True, authorization=auth_result, ...)
```

This is the **active enforcement point** for policy decisions.

### Runtime-Level Authorization (Available, Not Wired)

The `RuntimeAuthorizerCallback` class provides per-action authorization for `RuntimeAgent`:

```python
authorizer = create_demo_authorizer()
callback = create_runtime_authorizer(authorizer)
runtime = RuntimeAgent(
    runtime=agent_runtime,
    executor=executor,
    pre_action_authorizer=callback,  # Per-action gate
)
```

**Current limitation**: `PlannerExecutorAgent` doesn't expose `pre_action_authorizer`.
Runtime-level authorization requires either:
- SDK modification to add the parameter to `PlannerExecutorAgent`
- Switching to `RuntimeAgent` (larger refactor)

The `RuntimeAuthorizerCallback` is tested and ready for integration when SDK support is added.

## Testing Coverage and Gaps

### What's Tested

| Component | Test Coverage | Notes |
|-----------|---------------|-------|
| Authorization logic | Unit tests | `test_authorization.py` covers policy evaluation |
| Beat-level auth | Unit tests | Policy denials, allows, explicit deny rules |
| Runtime authorizer callback | Unit tests | `RuntimeAuthorizerCallback` tested in isolation |
| Workflow decision logic | Smoke tests | Success/failure branching with mocked browser/LLM |
| Provider creation | Unit tests | All provider types and configurations |
| Config loading | Unit tests | Environment variable parsing, defaults |

### What's NOT Tested (Verification Gaps)

| Gap | Description | Why |
|-----|-------------|-----|
| Full browser E2E | No tests use real browser + real DOM | Requires live site (localllamaland.com) |
| Visible-state predicates | Predicates tested with mocks, not live DOM | Snapshot selectors need real page |
| LLM response parsing | Mock LLM returns predetermined responses | Avoid non-determinism |
| Network errors/timeouts | Happy path only | Would require fault injection |
| Runtime-level auth integration | `RuntimeAuthorizerCallback` not wired to workflow | SDK limitation (see above) |

### Smoke Test Scope

The smoke tests in `tests/test_smoke.py` verify **workflow logic**, not visible state:

- **Normal success path logic** - workflow branches correctly when verification passes
- **Silent failure detection logic** - workflow recognizes verification failure as demo success
- **Denied action path logic** - pre-action authorization blocks execution

These tests mock the browser and LLM to ensure stability and speed. For live browser E2E tests,
use the separate `local-llama-land` test suite with an actual browser and target site.
