#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from pathlib import Path


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


def main() -> int:
    parser = argparse.ArgumentParser(description="Account Payable Demo scaffold entrypoint")
    parser.add_argument("--mode", choices=["local", "docker"], default=env("RUN_MODE", "local"))
    parser.add_argument("--llm", choices=["cloud", "local"], default=env("LLM_MODE", "cloud"))
    args = parser.parse_args()

    repo_dir = Path(__file__).resolve().parent

    print("====================================================================")
    print(" Account Payable Demo Scaffold")
    print("====================================================================")
    print(f"Repo:              {repo_dir}")
    print(f"Run mode:          {args.mode}")
    print(f"LLM mode:          {args.llm}")
    print(f"App base URL:      {env('APP_BASE_URL', 'https://www.localllamaland.com')}")
    print(f"Finance queue URL: {env('FINANCE_QUEUE_URL', 'https://www.localllamaland.com/demo/finance/queue')}")
    print(f"Sidecar URL:       {env('PREDICATE_SIDECAR_URL', 'http://localhost:8787')}")
    print(f"Policy file:       {repo_dir / env('SIDECAR_POLICY_PATH', './policy.yaml')}")
    print("--------------------------------------------------------------------")

    if args.llm == "local":
        print(f"Ollama base URL:   {env('OLLAMA_BASE_URL', 'http://localhost:11434')}")
        print(f"Planner model:     {env('OLLAMA_PLANNER_MODEL', 'qwen2.5:7b-instruct')}")
        print(f"Executor model:    {env('OLLAMA_EXECUTOR_MODEL', 'qwen2.5:4b-instruct')}")
    else:
        print(f"Planner provider:  {env('PLANNER_PROVIDER', 'openai')}")
        print(f"Planner model:     {env('PLANNER_MODEL', 'gpt-4o')}")
        print(f"Executor provider: {env('EXECUTOR_PROVIDER', 'openai')}")
        print(f"Executor model:    {env('EXECUTOR_MODEL', 'gpt-4o-mini')}")

    print("--------------------------------------------------------------------")
    print("This is the scaffold entrypoint only.")
    print("Next step: replace this file with the real PlannerExecutorAgent demo.")
    print("====================================================================")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
