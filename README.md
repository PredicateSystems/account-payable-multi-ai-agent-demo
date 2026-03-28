# Account Payable Demo

Flagship `predicate-secure` finance demo for `Invoice Exception Triage`.

This demo shows how Predicate Systems enables safe, verifiable agent workflows in finance operations—running entirely on **local LLMs** for data privacy and regulatory compliance.

## Demo Results

**Local LLM Configuration:**
- Planner: Qwen3:8B (5.2GB)
- Executor: Qwen3:4B (2.5GB)

| Beat | Status | Duration |
|------|--------|----------|
| Open Invoice & Add Note | ✅ PASS | 163s |
| Mark Reconciled (silent failure detection) | ✅ PASS | 41s |
| Release Payment (policy blocked) | ✅ BLOCKED | - |
| Route to Review | ✅ PASS | 33s |

**Key Metrics:**
- Total tokens: 12,884
- All beats succeeded as expected: ✅

### Why Local LLM Matters for Finance

Financial operations involve sensitive data—invoice amounts, vendor details, payment authorizations. This demo runs entirely on **local LLMs** with zero data leaving your infrastructure:

- **Data Privacy**: No invoice data, PO amounts, or vendor information sent to cloud APIs
- **Regulatory Compliance**: Meets data residency requirements for financial workflows
- **Cost Efficiency**: $0 LLM inference cost vs. ~$0.01-0.05 per workflow with cloud models

### How Predicate-Runtime Enables Small LLMs

Traditional browser automation requires large LLMs (70B+) to interpret raw HTML or screenshots. Predicate-runtime's **snapshot-first architecture** changes this:

1. **Structured Element Context**: The Predicate API extracts semantic elements with IDs, roles, and importance scores—no HTML parsing needed
2. **Compact Representation**: Elements formatted as `ID|role|text|importance|...` reduce context size by 90%+
3. **Domain Heuristics**: Common patterns (click "Add Note", "Mark Reconciled") bypass LLM entirely
4. **Tight Prompts**: Executor outputs just `CLICK(42)`—a 4B model handles this reliably

The result: A 4B executor model achieves the same reliability as GPT-4 on structured browser tasks, at a fraction of the cost and latency.

---

## Purpose

This demo proves three claims:

1. **Authorization claim**: agents should not be trusted to decide whether they are allowed to act
2. **Verification claim**: agents should not be trusted to report whether an action worked
3. **Deployment claim**: the same control model works with both cloud models and local small models

## Demo Story

The demo shows four beats:

1. **Normal flow**: agent opens invoice, compares fields, adds a note - verified
2. **Silent failure**: agent clicks "Mark Reconciled" but UI state doesn't change - verification fails
3. **Policy violation**: agent attempts "Release Payment" on high-value invoice - denied by policy
4. **Bounded fallback**: agent routes to review queue - allowed and verified

## Quick Start

### 1. Setup

```bash
# Enter the demo directory
cd predicate-secure/examples/account_payable_demo

# Copy environment template
cp .env.example .env

# Install dependencies
pip install -e ".[dev]"
```

### 2. Start the Policy Sidecar

The demo includes a policy file (`policy.yaml`) that enforces authorization rules. Run the Predicate sidecar to enable policy enforcement:

```bash
# Option A: If you have the sidecar binary
./predicate-authorityd --policy-file ./policy.yaml --web-ui run

# Option B: Build from rust-predicate-authorityd repo
cd /path/to/rust-predicate-authorityd
cargo build --release
./target/release/predicate-authorityd --policy-file /path/to/account_payable_demo/policy.yaml --web-ui run
```

The sidecar runs on `http://localhost:8787` by default. You can view the policy UI at `http://localhost:8787`.

**Policy highlights:**
- `deny-payment-release`: Blocks all payment release actions (demonstrates policy denial)
- `allow-invoice-actions`: Permits read, add_note, mark_reconciled, route_to_review

### 3. Configure LLM Mode

Edit `.env` to switch between cloud and local LLMs:

**For Local LLM (recommended for finance/privacy):**
```bash
# .env
LLM_MODE=local

# Ollama settings
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_PLANNER_MODEL=qwen3:8b
OLLAMA_EXECUTOR_MODEL=qwen3:4b
```

**For Cloud LLM:**
```bash
# .env
LLM_MODE=cloud

# Cloud provider settings
OPENAI_API_KEY=sk-...
PLANNER_PROVIDER=openai
PLANNER_MODEL=gpt-4o
EXECUTOR_PROVIDER=openai
EXECUTOR_MODEL=gpt-4o-mini
```

### 4. Run with Local Ollama

```bash
# Start Ollama (if not running)
ollama serve

# Pull required models (one-time)
ollama pull qwen3:8b
ollama pull qwen3:4b

# Run the demo
python main.py --run-workflow
```

### 5. Run with Cloud LLMs

```bash
# Ensure OPENAI_API_KEY is set in .env
python main.py --run-workflow
```

## Run Modes

### Local LLM (Recommended for Finance)

Best for data privacy and regulatory compliance. No data leaves your infrastructure.

```bash
# 1. Configure for local LLM
# Edit .env: LLM_MODE=local

# 2. Start Ollama and pull models
ollama serve
ollama pull qwen3:8b
ollama pull qwen3:4b

# 3. Start sidecar (in separate terminal)
./predicate-authorityd --policy-file ./policy.yaml --web-ui run

# 4. Run demo
python main.py --run-workflow
```

### Cloud LLM

Easiest setup, best quality. Requires API key.

```bash
# 1. Configure for cloud LLM
# Edit .env: LLM_MODE=cloud, OPENAI_API_KEY=sk-...

# 2. Start sidecar (in separate terminal)
./predicate-authorityd --policy-file ./policy.yaml --web-ui run

# 3. Run demo
python main.py --run-workflow
```

### Docker + Cloud

```bash
cp .env.example .env
./run-demo.sh --docker --llm cloud
```

### Docker + Local Ollama

Run Ollama on the host machine, then:

```bash
cp .env.example .env
OLLAMA_BASE_URL=http://host.docker.internal:11434 ./run-demo.sh --docker --llm local
```

### Local Shell + Cloud

```bash
cp .env.example .env
pip install -e ".[dev]"
python main.py --llm cloud
```

### Local Shell + Local Ollama

```bash
cp .env.example .env
ollama serve
python main.py --llm local
```

## Configuration

### Environment Variables

All configuration is loaded from `.env` or environment variables. See `.env.example` for full documentation.

Key settings:

| Variable | Description | Default |
|----------|-------------|---------|
| `RUN_MODE` | `local` or `docker` | `local` |
| `LLM_MODE` | `cloud` or `local` | `cloud` |
| `OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` |
| `PLANNER_PROVIDER` | Cloud planner provider | `openai` |
| `PLANNER_MODEL` | Planner model name | `gpt-4o` |
| `EXECUTOR_PROVIDER` | Cloud executor provider | `openai` |
| `EXECUTOR_MODEL` | Executor model name | `gpt-4o-mini` |

### CLI Options

```bash
python main.py --help

Options:
  --mode {local,docker}  Run mode (default: from env or 'local')
  --llm {cloud,local}    LLM mode (default: from env or 'cloud')
  --env-file PATH        Path to .env file
  --validate             Validate configuration and exit
  --debug                Enable debug output
```

## Package Structure

```
account_payable_demo/
├── account_payable_demo/       # Python package
│   ├── __init__.py             # Package exports
│   ├── config.py               # Configuration model and loading
│   └── providers.py            # LLM provider abstraction
├── tests/                      # Test suite
│   ├── test_config.py          # Configuration tests
│   └── test_providers.py       # Provider tests
├── main.py                     # Entrypoint
├── pyproject.toml              # Package configuration
├── requirements.txt            # Dependencies
├── .env.example                # Environment template
├── policy.yaml                 # Sidecar policy
├── run-demo.sh                 # Shell launcher
├── docker-compose.yml          # Docker configuration
├── DESIGN.md                   # System design
└── README.md                   # This file
```

## Configuration Model

The demo uses a hierarchical configuration model:

```
DemoConfig
├── run_mode: RunMode (local | docker)
├── llm_mode: LLMMode (cloud | local)
├── ollama: OllamaConfig
│   ├── base_url
│   ├── planner_model
│   └── executor_model
├── cloud_llm: CloudLLMConfig
│   ├── planner_provider
│   ├── planner_model
│   ├── executor_provider
│   ├── executor_model
│   └── api_keys (openai, anthropic, deepinfra)
├── sidecar: SidecarConfig
│   ├── url
│   ├── policy_path
│   └── version
├── app: AppConfig
│   ├── base_url
│   └── finance_queue_url
└── runtime options (headless, debug, output dirs)
```

## Provider Selection

The demo supports multiple LLM providers:

| Provider | Type | Use Case |
|----------|------|----------|
| `ollama` | Local | Privacy-sensitive, local development |
| `openai` | Cloud | Best quality, easiest setup |
| `anthropic` | Cloud | Alternative cloud provider |
| `deepinfra` | Cloud | Cost-effective inference |

Provider selection is based on `LLM_MODE`:
- `local`: Uses Ollama for both planner and executor
- `cloud`: Uses configured cloud providers (can be mixed)

## Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=account_payable_demo

# Run specific test file
pytest tests/test_config.py -v
```

## Development

### Validate Configuration

```bash
python main.py --validate
```

### Debug Mode

```bash
python main.py --debug
```

This prints detailed provider configuration including:
- Provider type and model for each role
- Base URLs and API key status
- Full configuration dump

## Sidecar Policy

The demo ships with a pre-created policy in `policy.yaml`. In local mode, `run-demo.sh` can attempt to download the correct sidecar binary for the host platform and run it against this policy.

## Next Implementation Steps

1. ~~Build the finance routes in `local-llama-land`~~ (Done)
2. ~~Replace the placeholder Python entrypoint with config/provider scaffold~~ (Done)
3. Implement the PlannerExecutorAgent workflow
4. Wire `predicate-secure` sidecar integration
5. Add `predicate-runtime` verification
6. Record the 2-3 minute GTM demo

## Related Documentation

- [DESIGN.md](DESIGN.md) - System design and deployment matrix

## Related Repositories

- [predicate-runtime SDK (Python)](https://github.com/PredicateSystems/predicate-runtime-python) - Browser automation with snapshot-first architecture
- [predicate-secure SDK (Python)](https://github.com/PredicateSystems/predicate-secure) - Policy enforcement and verification layer
- [predicate-authority-sidecar (Rust)](https://github.com/PredicateSystems/predicate-authority-sidecar) - Authorization sidecar for policy decisions
