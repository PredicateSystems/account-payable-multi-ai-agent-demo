# Account Payable Demo

Flagship `predicate-secure` finance demo for `Invoice Exception Triage`.

This repo is the execution scaffold for the finance demo described in:

- `DESIGN.md`
- `../../../docs/predicate_secure/2026-03-27_finance_ops_invoice_exception_triage_demo_spec.md`

## Purpose

This demo is designed to show four things in one tight workflow:

1. a normal allowed action succeeds
2. a valid action silently fails because the UI state never changed
3. a risky action is denied by policy before execution
4. a bounded fallback action is allowed and verified

The goal is not to show a generic agent. The goal is to show that:

`agents are not trustworthy enough to self-authorize or self-verify`

## Current Scaffold

This repo currently provides:

- deployment matrix and design doc
- demo environment configuration templates
- pre-created sidecar policy
- `run-demo.sh` with local and Docker modes
- a lightweight Python entrypoint scaffold

It does not yet contain the full finance workflow implementation.

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
python3 -m venv .venv
source .venv/bin/activate
./run-demo.sh --local --llm cloud
```

### Local Shell + Local Ollama

```bash
cp .env.example .env
ollama serve
./run-demo.sh --local --llm local
```

## Environment

Copy `.env.example` to `.env` and set the values you need.

Important variables:

- `LLM_MODE=cloud|local`
- `OLLAMA_BASE_URL`
- `OPENAI_API_KEY`
- `DEEPINFRA_API_KEY`
- `PREDICATE_SIDECAR_URL`
- `SIDECAR_VERSION`

## Sidecar Policy

The demo ships with a pre-created policy:

- `policy.yaml`

In local mode, `run-demo.sh` can attempt to download the correct sidecar binary for the host platform and run it against this policy.

## Files

- `DESIGN.md`: system design and setup matrix
- `.env.example`: environment template
- `.gitignore`: standard ignore rules
- `policy.yaml`: demo sidecar policy scaffold
- `run-demo.sh`: launcher for local and Docker modes
- `main.py`: lightweight entrypoint scaffold
- `docker-compose.yml`: minimal runner container scaffold

## Next Implementation Steps

1. Build the finance routes in `local-llama-land`
2. Replace the placeholder Python entrypoint with the real planner/executor demo
3. Wire `predicate-secure` and `predicate-runtime` to the sidecar policy
4. Add the exact silent-failure UI path in the finance demo surface
5. Record the 2-3 minute GTM demo
