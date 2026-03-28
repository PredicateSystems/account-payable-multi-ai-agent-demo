#!/usr/bin/env python3
"""Account Payable Demo - main entrypoint."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from account_payable_demo import DemoConfig, load_config
from account_payable_demo.config import LLMMode, RunMode
from account_payable_demo.providers import get_provider_for_role, validate_provider_config


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Account Payable Demo - Predicate Systems finance workflow demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with cloud LLMs (default)
  python main.py --llm cloud

  # Run with local Ollama
  python main.py --llm local

  # Docker mode with cloud LLMs
  python main.py --mode docker --llm cloud

Environment variables:
  See .env.example for full configuration options.
        """,
    )
    parser.add_argument(
        "--mode",
        choices=["local", "docker"],
        default=None,
        help="Run mode: local shell or Docker (default: from RUN_MODE env or 'local')",
    )
    parser.add_argument(
        "--llm",
        choices=["cloud", "local"],
        default=None,
        help="LLM mode: cloud providers or local Ollama (default: from LLM_MODE env or 'cloud')",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        default=None,
        help="Path to .env file (default: .env in current directory)",
    )
    parser.add_argument(
        "--validate",
        action="store_true",
        help="Validate configuration and exit",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode",
    )
    return parser.parse_args()


def print_config(config: DemoConfig) -> None:
    """Print the current configuration."""
    repo_dir = Path(__file__).resolve().parent

    print("=" * 70)
    print(" Account Payable Demo")
    print("=" * 70)
    print(f"Repo:              {repo_dir}")
    print(f"Run mode:          {config.run_mode.value}")
    print(f"LLM mode:          {config.llm_mode.value}")
    print("-" * 70)

    # App config
    print(f"App base URL:      {config.app.base_url}")
    print(f"Finance queue URL: {config.app.finance_queue_url}")
    print("-" * 70)

    # Sidecar config
    print(f"Sidecar URL:       {config.sidecar.url}")
    print(f"Policy file:       {config.sidecar.policy_path}")
    print("-" * 70)

    # LLM config
    if config.is_local_llm:
        print("LLM Provider: Ollama (local)")
        print(f"  Base URL:        {config.ollama.base_url}")
        print(f"  Planner model:   {config.ollama.planner_model}")
        print(f"  Executor model:  {config.ollama.executor_model}")
    else:
        print("LLM Provider: Cloud")
        print(f"  Planner:         {config.cloud_llm.planner_provider} / {config.cloud_llm.planner_model}")
        print(f"  Executor:        {config.cloud_llm.executor_provider} / {config.cloud_llm.executor_model}")

        # Show API key status (not the actual keys)
        planner_key = config.cloud_llm.get_api_key(config.cloud_llm.planner_provider)
        executor_key = config.cloud_llm.get_api_key(config.cloud_llm.executor_provider)
        print(f"  Planner API key: {'[set]' if planner_key else '[missing]'}")
        print(f"  Executor API key: {'[set]' if executor_key else '[missing]'}")

    print("-" * 70)

    # Runtime config
    print(f"Headless:          {config.headless}")
    print(f"Debug:             {config.debug}")
    print(f"Trace output:      {config.trace_output_dir}")
    print(f"Artifact output:   {config.artifact_output_dir}")
    print("=" * 70)


def print_provider_details(config: DemoConfig) -> None:
    """Print detailed provider information."""
    print("\nProvider Details:")
    print("-" * 70)

    planner = get_provider_for_role(config, "planner")
    executor = get_provider_for_role(config, "executor")

    print(f"Planner provider:")
    print(f"  Type:     {planner.provider_type.value}")
    print(f"  Model:    {planner.model}")
    print(f"  Is local: {planner.is_local}")
    if planner.base_url:
        print(f"  Base URL: {planner.base_url}")

    print(f"\nExecutor provider:")
    print(f"  Type:     {executor.provider_type.value}")
    print(f"  Model:    {executor.model}")
    print(f"  Is local: {executor.is_local}")
    if executor.base_url:
        print(f"  Base URL: {executor.base_url}")

    print("-" * 70)


def main() -> int:
    """Main entrypoint."""
    args = parse_args()
    repo_dir = Path(__file__).resolve().parent

    # Load configuration
    config = load_config(
        env_file=args.env_file,
        base_dir=repo_dir,
    )

    # Override from CLI args
    if args.mode:
        config.run_mode = RunMode(args.mode)
    if args.llm:
        config.llm_mode = LLMMode(args.llm)
    if args.debug:
        config.debug = True

    # Validate configuration
    errors = validate_provider_config(config)

    # Print configuration
    print_config(config)

    if config.debug:
        print_provider_details(config)

    # Report validation errors
    if errors:
        print("\nConfiguration Warnings:")
        for error in errors:
            print(f"  - {error}")

    if args.validate:
        if errors:
            print("\nValidation failed.")
            return 1
        print("\nConfiguration is valid.")
        return 0

    # Placeholder for actual workflow execution
    print("\n" + "=" * 70)
    print(" Demo Workflow (not yet implemented)")
    print("=" * 70)
    print("This is the configuration and provider selection scaffold.")
    print("Next step: implement the PlannerExecutorAgent workflow.")
    print("=" * 70)

    return 0


if __name__ == "__main__":
    sys.exit(main())
