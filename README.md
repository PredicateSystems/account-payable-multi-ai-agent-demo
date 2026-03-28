# Account Payable Demo

Flagship `predicate-secure` finance demo for `Invoice Exception Triage`.

This demo shows how Predicate Systems enables safe, verifiable agent workflows in finance operations.

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

### 2. Run with Cloud LLMs

```bash
# Set your API key in .env
# OPENAI_API_KEY=sk-...

# Run the demo
python main.py --llm cloud
```

### 3. Run with Local Ollama

```bash
# Start Ollama (if not running)
ollama serve

# Pull required models
ollama pull qwen2.5:7b-instruct
ollama pull qwen2.5:4b-instruct

# Run the demo
python main.py --llm local
```

## Run Modes

### Docker + Cloud

Recommended first-run path.

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
- [Spec](../../../docs/predicate_secure/2026-03-27_finance_ops_invoice_exception_triage_demo_spec.md) - Full demo specification
