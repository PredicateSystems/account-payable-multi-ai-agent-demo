# Account Payable Demo Claude Implementation Prompts

This file contains step-by-step prompts to hand off implementation to Claude.

The prompts are intentionally small and sequential. Each one should be run after the previous step is completed and verified.

## Working Context

### Primary demo repo

- `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo`

### Finance UI target

- `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land`

### Reference docs

- `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/DESIGN.md`
- `/Users/guoliangwang/Code/Sentience/docs/predicate_secure/2026-03-27_finance_ops_invoice_exception_triage_demo_spec.md`
- `/Users/guoliangwang/Code/Sentience/docs/predicate_secure/2026-03-27_multi_agent_demo_brainstorm.md`

### Relevant SDK / policy repos

- `/Users/guoliangwang/Code/Sentience/sdk-python`
- `/Users/guoliangwang/Code/Sentience/rust-predicate-authorityd`
- `/Users/guoliangwang/Code/Sentience/predicate-secure/py-predicate-secure`

## Implementation Strategy

Build this in two parallel tracks:

1. `local-llama-land` finance UI surface
2. `account_payable_demo` runner, policy, and demo orchestration

Keep the first version narrow:

- one normal flow
- one silent verification failure
- one denied risky action
- one corrected bounded fallback action

Every step below includes test expectations. Claude should add tests as it implements each step.

---

# Prompt 1: Set up finance UI routes and test harness

## Goal

Create the base finance demo route structure inside `local-llama-land`, plus a minimal frontend test setup so future UI work has coverage.

## Files and directories

- Modify: `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/package.json`
- Create: `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/vitest.config.ts`
- Create: `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/tests/setup.ts`
- Create: `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/app/demo/finance/page.tsx`
- Create: `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/app/demo/finance/queue/page.tsx`
- Create: `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/app/demo/finance/review/page.tsx`
- Create any shared finance UI components under:
  - `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/components/finance/`
- Create tests under:
  - `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/tests/finance/`

## Requirements

- Add a minimal finance namespace under `app/demo/finance`
- Add a simple landing page linking to queue and review routes
- Add a queue page with realistic invoice rows and statuses
- Add a review page with at least one routed invoice example
- Keep data local and hardcoded for now
- Add a frontend test harness with `vitest` and `@testing-library/react`
- Add at least 2 tests:
  - finance landing renders expected navigation
  - queue page renders invoice list and statuses

## Test commands

Claude should add or update scripts so these work:

```bash
cd /Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land
npm install
npm test
```

## Prompt to Claude

```text
Implement the initial finance demo route scaffold in `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land`.

Context:
- This app will host the finance UI surface for the Account Payable demo.
- Follow the finance demo spec in:
  - `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/DESIGN.md`
  - `/Users/guoliangwang/Code/Sentience/docs/predicate_secure/2026-03-27_finance_ops_invoice_exception_triage_demo_spec.md`
- Keep the first version narrow and deterministic.

Tasks:
1. Add a minimal test setup for this Next.js app using Vitest and Testing Library.
2. Create these routes:
   - `app/demo/finance/page.tsx`
   - `app/demo/finance/queue/page.tsx`
   - `app/demo/finance/review/page.tsx`
3. Add any reusable finance components under `components/finance/`.
4. Hardcode a few realistic invoice rows with statuses like `Open`, `Exception`, `Needs Review`, `Reconciled`.
5. Add at least 2 tests:
   - landing page shows finance demo entry points
   - queue page renders invoice rows and visible statuses

Constraints:
- Keep implementation simple and production-looking, not a full ERP clone.
- Use realistic finance labels.
- Do not build backend/API layers yet.
- Use ASCII only unless existing files require otherwise.

When done:
- run the tests
- summarize what was added
```

---

# Prompt 2: Build invoice detail and vendor comparison pages

## Goal

Add the two core pages the agent will use for reconciliation: invoice detail and vendor/supporting record view.

## Files and directories

- Create: `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/app/demo/finance/invoices/[id]/page.tsx`
- Create: `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/app/demo/finance/vendor/[id]/page.tsx`
- Create or modify shared components and fixtures under:
  - `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/components/finance/`
  - `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/lib/`
- Create tests under:
  - `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/tests/finance/`

## Requirements

- Invoice detail page must show deterministic fields:
  - invoice number
  - vendor
  - amount
  - due date
  - PO reference
  - reconciliation status
  - payment status
  - notes/activity panel
- Vendor page must show corresponding comparison fields
- Pages should look like separate systems but live under the same app
- Add tests that verify key visible fields render correctly

## Prompt to Claude

```text
Implement the finance reconciliation surfaces in `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land`.

Add:
- `app/demo/finance/invoices/[id]/page.tsx`
- `app/demo/finance/vendor/[id]/page.tsx`

Requirements:
- Make the invoice detail page feel like the main ERP/AP system
- Make the vendor page feel like a secondary external or supporting system
- Include deterministic visible fields that Predicate can verify later:
  - invoice number
  - vendor name
  - billed amount
  - invoice date
  - PO reference
  - payment status
  - reconciliation status
  - activity/notes area
- Use shared mock data in a maintainable way
- Add at least 2 tests covering field rendering and route-specific content

Constraints:
- No backend yet
- Keep all data local and static
- Make the DOM readable and testable
- Prefer small reusable components over a giant page file

After implementation:
- run tests
- summarize which selectors / visible labels are now stable enough for runtime verification
```

---

# Prompt 3: Add the purposeful silent-failure path

## Goal

Engineer the most important demo moment: `Mark Reconciled` appears to work, but the visible UI state does not change.

## Files and directories

- Modify invoice detail components/pages under:
  - `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/app/demo/finance/invoices/[id]/page.tsx`
  - `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/components/finance/`
- Add tests under:
  - `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/tests/finance/`

## Requirements

- Add a controlled scenario where clicking `Mark Reconciled` does not update visible status
- Keep the action visible and plausible
- Make it easy for the runtime to verify failure by checking that status text did not change
- Add tests proving:
  - the click path can be triggered
  - the visible status remains unchanged in the failure case

## Prompt to Claude

```text
Add the purposeful silent-failure path to the finance invoice detail UI in `local-llama-land`.

This is the key product moment of the entire demo.

Requirements:
- `Mark Reconciled` should appear clickable
- under a controlled condition, clicking it should not update the visible reconciliation status
- keep the UI realistic: modal, stale overlay, no-op transition, or blocked commit are all acceptable
- the visible DOM must make the failure easy to verify deterministically

Testing requirements:
- add tests for the failure path
- confirm the click handler runs or the UI path triggers
- confirm the visible status text does NOT change

Constraints:
- this should feel like a realistic UI failure, not a broken toy
- keep the implementation local and deterministic
- do not add full app state management complexity

After implementation:
- explain the exact visible predicate(s) a runtime test could use to prove failure
```

---

# Prompt 4: Add the risky action and bounded fallback path

## Goal

Add the high-risk action (`Release Payment`) and the safe fallback path (`Route To Review` / add note), with UI state transitions that are easy to verify.

## Files and directories

- Modify:
  - `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/app/demo/finance/invoices/[id]/page.tsx`
  - `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/app/demo/finance/review/page.tsx`
  - `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/components/finance/`
- Tests:
  - `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/tests/finance/`

## Requirements

- Add a visible high-risk action surface:
  - `Release Payment`
- Add safe fallback actions:
  - add note
  - route to review
- Routing to review must visibly update review queue or invoice state
- Add tests:
  - route-to-review changes visible state
  - note appears in activity panel

## Prompt to Claude

```text
Implement the bounded fallback flow for the finance demo UI in `local-llama-land`.

Add:
- a visible risky action: `Release Payment`
- safe fallback actions:
  - add note
  - route to review

Requirements:
- `Release Payment` should exist in the UI so policy denial is meaningful later
- safe fallback actions should visibly change state in a deterministic way
- routing to review should be reflected either on the invoice page or review queue page
- notes should appear in the activity stream

Testing requirements:
- add tests showing:
  - note creation updates visible UI
  - route-to-review updates visible UI

Constraints:
- no sidecar integration yet
- keep this step focused on browser-visible state only

After implementation:
- list the exact visible predicates that would prove the fallback action succeeded
```

---

# Prompt 5: Add Python packaging, config loading, and provider selection

## Goal

Replace the placeholder `main.py` scaffold with a real config-aware launcher skeleton that supports cloud and local providers cleanly, but still stops short of full workflow automation.

## Files and directories

- Modify:
  - `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/main.py`
  - `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/.env.example`
  - `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/README.md`
- Create:
  - `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/requirements.txt`
  - `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/account_payable_demo/`
  - `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/tests/`

## Requirements

- create a small Python package structure
- load `.env`
- implement provider selection for:
  - cloud
  - local Ollama-compatible path
- expose planner and executor model config
- add pytest coverage for config parsing and provider selection behavior

## Prompt to Claude

```text
Refactor the Python demo scaffold in `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo` into a small testable package.

Tasks:
1. Replace the placeholder `main.py` with a package-based structure.
2. Add config loading from `.env` and environment variables.
3. Implement a clean configuration model for:
   - run mode
   - llm mode
   - planner model
   - executor model
   - app base URL
   - sidecar URL
4. Add provider selection logic that can support:
   - cloud providers
   - local Ollama-compatible provider path
5. Add pytest coverage for config parsing and provider selection.

Constraints:
- keep this step focused on configuration and provider abstraction
- do not implement the full planner/executor workflow yet
- use the existing Predicate Python SDK as the integration target

Tests:
- add pytest tests under `tests/`
- run the test suite

When done:
- summarize the package structure and the config contract
```

---

# Prompt 6: Implement sidecar bootstrap and launcher behavior in Python-friendly modules

## Goal

Move the core sidecar bootstrap logic out of shell-only behavior and into testable Python or shell helpers, keeping `run-demo.sh` as the user-facing entrypoint.

## Files and directories

- Modify:
  - `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/run-demo.sh`
- Create:
  - `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/account_payable_demo/sidecar.py`
  - `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/tests/test_sidecar.py`

## Requirements

- centralize:
  - OS/arch detection
  - sidecar release resolution
  - download behavior
  - health checks
- keep manual fallback behavior
- add tests for:
  - platform mapping
  - release URL resolution logic
  - health-check helpers

## Prompt to Claude

```text
Refactor the account payable demo sidecar bootstrap logic into a testable module.

Context:
- `run-demo.sh` should remain the user-facing launcher
- but platform detection, release resolution, and health checks should live in testable code

Tasks:
1. Add `account_payable_demo/sidecar.py`
2. Move sidecar bootstrap logic into Python helpers where practical
3. Keep `run-demo.sh` thin and user-friendly
4. Add tests for:
   - OS and architecture normalization
   - release asset selection logic
   - sidecar health-check behavior

Constraints:
- do not make the installer overly clever
- support a clear manual fallback path
- keep sidecar version pinning explicit

After implementation:
- run tests
- summarize the exact local bootstrap behavior
```

---

# Prompt 7: Implement the real PlannerExecutorAgent demo flow

## Goal

Wire up the actual Python demo using `predicate-runtime` `PlannerExecutorAgent`, with cloud/local model support and the finance UI target in `local-llama-land`.

## Files and directories

- Modify or create in:
  - `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/account_payable_demo/`
  - `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/main.py`
  - `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/tests/`

## Requirements

- use Python SDK `PlannerExecutorAgent`
- point browser task at:
  - `https://www.localllamaland.com/demo/finance/queue`
  - or localhost equivalent for local app development
- configure planner + executor providers from env
- create the bounded demo workflow:
  - normal action
  - silent verification failure
  - risky action attempt
  - bounded fallback
- add tests for plan-building helpers and predicate construction where feasible

## Prompt to Claude

```text
Implement the real finance demo runner using the Predicate Python SDK in `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo`.

Requirements:
- use `PlannerExecutorAgent` from `sdk-python`
- use the finance UI in `local-llama-land` as the browser target
- support both cloud and local model modes from config
- structure the workflow around the 4 demo beats:
  1. normal flow
  2. silent verification failure
  3. policy violation
  4. corrected bounded fallback action

Implementation expectations:
- use `AutomationTask` or equivalent SDK abstractions where appropriate
- add deterministic verification predicates for visible state
- keep the first implementation narrow and explicit
- do not overgeneralize into a full product framework

Testing:
- add unit tests for helper functions and predicate-building logic
- if direct browser e2e coverage is too heavy for this step, keep tests focused and deterministic

After implementation:
- document the exact browser target URLs and visible predicates used
```

---

# Prompt 8: Integrate predicate-secure / sidecar authorization boundaries

## Goal

Add the authorization layer so the demo meaningfully exercises the policy and denied risky action path.

## Files and directories

- Modify:
  - `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/policy.yaml`
  - Python demo package files in `account_payable_demo/`
  - `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/tests/`

## Requirements

- integrate pre-execution authorization through `predicate-secure` or direct sidecar calls
- ensure risky action denial is surfaced clearly
- keep the allowed note/review actions working
- add tests around authorization-request building and denial handling

## Prompt to Claude

```text
Integrate the authorization layer into the account payable demo.

Goal:
- the risky action in the demo must be denied by policy before execution
- safe fallback actions must remain allowed

Tasks:
1. Wire the demo runner to `predicate-secure` or direct sidecar authorization calls
2. Use the pre-created `policy.yaml`
3. Make sure the denied risky action is surfaced clearly in logs/output
4. Keep the bounded fallback action path intact
5. Add tests for:
   - authorization request construction
   - denial handling
   - allowed action path behavior where feasible

Constraints:
- keep the policy story simple and explicit
- do not overbuild a general auth framework in the demo repo

After implementation:
- summarize the exact denied action and the exact allowed fallback actions
```

---

# Prompt 9: Add end-to-end demo verification and smoke tests

## Goal

Add the highest-value smoke coverage for the whole demo system.

## Files and directories

- Add tests in:
  - `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/tests/`
- Potentially add lightweight browser tests in:
  - `/Users/guoliangwang/Code/Sentience/sentience-sdk-playground/local-llama-land/tests/`

## Requirements

- add at least one smoke path for:
  - normal flow visible state
  - silent failure detection helper path
  - denied action path
- do not require full production-like e2e complexity if it slows iteration too much

## Prompt to Claude

```text
Add smoke-level test coverage across the account payable demo.

Priorities:
1. cover the normal visible-state success path
2. cover the silent verification failure path
3. cover the denied risky action path

Constraints:
- keep tests deterministic
- prefer a few high-signal tests over a large brittle suite
- avoid overengineering browser e2e if unit + focused integration tests provide enough confidence

When done:
- list what remains untested and why
- summarize the exact verification gap, if any
```

---

# Prompt 10: Final polish for handoff and GTM readiness

## Goal

Make the repo easy for an external user to run and understand.

## Files and directories

- Modify:
  - `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/README.md`
  - `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/DESIGN.md`
  - `/Users/guoliangwang/Code/Sentience/predicate-secure/examples/account_payable_demo/.env.example`

## Requirements

- update README to match the actual implementation
- include exact run commands for all 4 deployment modes
- document local sidecar fallback behavior
- document cloud/local model examples
- keep it short and runnable

## Prompt to Claude

```text
Polish the account payable demo repo for external users.

Tasks:
1. Update README to reflect the actual implementation
2. Keep setup instructions concise and copy/pasteable
3. Document:
   - docker + cloud
   - docker + local Ollama
   - local + cloud
   - local + local Ollama
4. Document local sidecar auto-download behavior and manual fallback
5. Make sure `.env.example` matches the implemented config

Constraints:
- optimize for first-time users
- keep the README concise
- avoid internal-only jargon where possible

After implementation:
- provide a short release-readiness checklist
```

---

## Recommended Execution Order

Run the prompts in this order:

1. Prompt 1
2. Prompt 2
3. Prompt 3
4. Prompt 4
5. Prompt 5
6. Prompt 6
7. Prompt 7
8. Prompt 8
9. Prompt 9
10. Prompt 10

## Recommended Stop Points

If you want faster iteration, stop and review after:

- Prompt 4: finance UI is ready enough for browser-driven work
- Prompt 6: launcher/bootstrap story is in place
- Prompt 8: full control-plane story is visible

## Notes For Claude

- Keep the demo narrow and memorable
- Prefer deterministic visible state over hidden backend logic
- Do not expand into a full ERP clone
- The most important product moment is the silent verification failure
- The best framing is:
  - `valid action, wrong state`
  - `agents lie, we verify what changed`
