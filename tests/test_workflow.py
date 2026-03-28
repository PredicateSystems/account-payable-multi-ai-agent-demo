"""Tests for the demo workflow module.

These tests follow the 'soft plans, hard predicates' design:
- Focus on verification outcomes, not step choreography
- Tasks define objectives, planner generates the steps
- Verification predicates are deterministic hard outcomes
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from predicate.agents import AutomationTask, TaskCategory

from account_payable_demo.config import CloudLLMConfig, DemoConfig, LLMMode, OllamaConfig
from account_payable_demo.workflow import (
    BeatResult,
    DemoBeat,
    WorkflowResult,
    build_demo_plan_step,
    build_predicate_spec,
    create_sdk_provider,
    get_beat_1_task,
    get_beat_1_verification,
    get_beat_2_task,
    get_beat_2_verification,
    get_beat_3_task,
    get_beat_3_verification,
    get_beat_4_task,
    get_beat_4_verification,
)


class TestDemoBeat:
    """Tests for DemoBeat enum aligned with finance demo story."""

    def test_all_beats_defined(self):
        """Test that all 4 demo beats are defined."""
        assert len(DemoBeat) == 4
        assert DemoBeat.OPEN_AND_NOTE.value == "open_and_note"
        assert DemoBeat.MARK_RECONCILED.value == "mark_reconciled"
        assert DemoBeat.RELEASE_PAYMENT.value == "release_payment"
        assert DemoBeat.ROUTE_TO_REVIEW.value == "route_to_review"

    def test_beat_names_match_finance_demo_story(self):
        """Test beats match the intended finance demo narrative."""
        # Beat 1: Normal action - open invoice, compare, add note
        assert "note" in DemoBeat.OPEN_AND_NOTE.value

        # Beat 2: Silent failure - Mark Reconciled appears to work but doesn't
        assert "reconciled" in DemoBeat.MARK_RECONCILED.value

        # Beat 3: Risky action blocked by policy
        assert "payment" in DemoBeat.RELEASE_PAYMENT.value

        # Beat 4: Safe fallback action succeeds
        assert "review" in DemoBeat.ROUTE_TO_REVIEW.value


class TestBeatResult:
    """Tests for BeatResult dataclass."""

    def test_successful_beat_result(self):
        """Test creating a successful beat result."""
        result = BeatResult(
            beat=DemoBeat.OPEN_AND_NOTE,
            success=True,
            details={"verification_passed": True},
        )
        assert result.beat == DemoBeat.OPEN_AND_NOTE
        assert result.success is True
        assert result.error is None
        assert result.details["verification_passed"] is True

    def test_failed_beat_result(self):
        """Test creating a failed beat result."""
        result = BeatResult(
            beat=DemoBeat.RELEASE_PAYMENT,
            success=False,
            error="Policy violation",
        )
        assert result.beat == DemoBeat.RELEASE_PAYMENT
        assert result.success is False
        assert result.error == "Policy violation"

    def test_silent_failure_beat_result(self):
        """Test beat result for expected silent failure (Beat 2)."""
        # Beat 2 succeeds as a demo when verification FAILS
        # (the UI didn't change even though button was clicked)
        result = BeatResult(
            beat=DemoBeat.MARK_RECONCILED,
            success=True,  # Demo succeeded
            details={
                "verification_passed": False,  # Status didn't change (expected)
                "fallback_used": False,
            },
        )
        assert result.beat == DemoBeat.MARK_RECONCILED
        assert result.success is True
        assert result.details["verification_passed"] is False


class TestWorkflowResult:
    """Tests for WorkflowResult dataclass."""

    def test_empty_workflow_result(self):
        """Test empty workflow result."""
        result = WorkflowResult()
        assert result.beats == []
        assert result.total_tokens == 0
        assert result.trace_file is None
        assert result.all_succeeded is True  # Empty = all succeeded

    def test_workflow_result_all_succeeded(self):
        """Test workflow result where all beats succeed."""
        result = WorkflowResult(
            beats=[
                BeatResult(beat=DemoBeat.OPEN_AND_NOTE, success=True),
                BeatResult(beat=DemoBeat.MARK_RECONCILED, success=True),
                BeatResult(beat=DemoBeat.RELEASE_PAYMENT, success=True),
                BeatResult(beat=DemoBeat.ROUTE_TO_REVIEW, success=True),
            ],
            total_tokens=1500,
        )
        assert result.all_succeeded is True
        assert result.total_tokens == 1500

    def test_workflow_result_some_failed(self):
        """Test workflow result where some beats fail."""
        result = WorkflowResult(
            beats=[
                BeatResult(beat=DemoBeat.OPEN_AND_NOTE, success=True),
                BeatResult(beat=DemoBeat.MARK_RECONCILED, success=False),
            ],
        )
        assert result.all_succeeded is False


class TestBeatTaskDefinitions:
    """Tests for beat task definitions (soft plans).

    Tasks define WHAT to accomplish, not HOW.
    The planner generates the intermediate steps.
    """

    def test_beat_1_task_objective(self):
        """Test Beat 1 task defines objective, not steps."""
        task = get_beat_1_task()
        assert task.task_id == "beat-1-open-and-note"
        assert "localllamaland.com/demo/finance/queue" in task.starting_url
        assert task.category == TaskCategory.FORM_FILL
        # Task describes objective
        assert "invoice" in task.task.lower()
        assert "note" in task.task.lower()
        # Goal captures intent
        assert task.goal.get("action") == "add_note"

    def test_beat_2_task_objective(self):
        """Test Beat 2 task defines mark reconciled objective."""
        task = get_beat_2_task()
        assert task.task_id == "beat-2-mark-reconciled"
        # Task describes the action
        assert "mark reconciled" in task.task.lower()
        assert "status" in task.task.lower()
        # Goal captures intent
        assert task.goal.get("action") == "mark_reconciled"

    def test_beat_3_task_objective(self):
        """Test Beat 3 task defines release payment objective."""
        task = get_beat_3_task()
        assert task.task_id == "beat-3-release-payment"
        # Task describes risky action
        assert "payment" in task.task.lower()
        assert task.category == TaskCategory.TRANSACTION  # High-risk category
        # Goal captures intent
        assert task.goal.get("action") == "release_payment"

    def test_beat_4_task_objective(self):
        """Test Beat 4 task defines route to review objective."""
        task = get_beat_4_task()
        assert task.task_id == "beat-4-route-to-review"
        # Task describes safe fallback
        assert "review" in task.task.lower()
        # Goal captures intent
        assert task.goal.get("action") == "route_to_review"

    def test_all_tasks_target_same_url(self):
        """Test all tasks start from the finance queue."""
        tasks = [
            get_beat_1_task(),
            get_beat_2_task(),
            get_beat_3_task(),
            get_beat_4_task(),
        ]
        for task in tasks:
            assert "localllamaland.com/demo/finance/queue" in task.starting_url


class TestVerificationPredicates:
    """Tests for verification predicates (hard outcomes).

    These are deterministic checks that verify task success.
    """

    def test_beat_1_verification_checks_note(self):
        """Test Beat 1 verification checks for notes."""
        predicates = get_beat_1_verification()
        assert len(predicates) >= 1
        # Should check URL and note presence
        # Verification should include existence checks
        assert len(predicates) >= 2

    def test_beat_2_verification_checks_status(self):
        """Test Beat 2 verification checks reconciled status."""
        predicates = get_beat_2_verification()
        assert len(predicates) >= 1
        # Should check for reconciled status indicator
        # This verification is expected to FAIL in the demo
        # (demonstrating silent failure detection)

    def test_beat_3_verification_handles_block(self):
        """Test Beat 3 verification handles policy block or success."""
        predicates = get_beat_3_verification()
        assert len(predicates) >= 1
        # Should use any_of to accept either success or policy block

    def test_beat_4_verification_checks_review_status(self):
        """Test Beat 4 verification checks for review status."""
        predicates = get_beat_4_verification()
        assert len(predicates) >= 1
        # Should check for review status indicators


class TestCreateSdkProvider:
    """Tests for create_sdk_provider helper."""

    def test_create_openai_provider(self):
        """Test creating OpenAI provider."""
        config = DemoConfig(
            llm_mode=LLMMode.CLOUD,
            cloud_llm=CloudLLMConfig(
                planner_provider="openai",
                planner_model="gpt-4o",
                executor_provider="openai",
                executor_model="gpt-4o-mini",
                openai_api_key="test-key",
            ),
        )

        with patch("account_payable_demo.workflow.OpenAIProvider") as mock_provider:
            mock_instance = MagicMock()
            mock_provider.return_value = mock_instance

            provider = create_sdk_provider(config, "planner")

            mock_provider.assert_called_once_with(
                model="gpt-4o",
                api_key="test-key",
            )
            assert provider == mock_instance

    def test_create_anthropic_provider(self):
        """Test creating Anthropic provider."""
        config = DemoConfig(
            llm_mode=LLMMode.CLOUD,
            cloud_llm=CloudLLMConfig(
                planner_provider="anthropic",
                planner_model="claude-3-sonnet",
                executor_provider="anthropic",
                executor_model="claude-3-haiku",
                anthropic_api_key="test-anthropic-key",
            ),
        )

        with patch("account_payable_demo.workflow.AnthropicProvider") as mock_provider:
            mock_instance = MagicMock()
            mock_provider.return_value = mock_instance

            create_sdk_provider(config, "planner")

            mock_provider.assert_called_once_with(
                model="claude-3-sonnet",
                api_key="test-anthropic-key",
            )

    def test_create_ollama_provider(self):
        """Test creating Ollama provider (OpenAI-compatible)."""
        config = DemoConfig(
            llm_mode=LLMMode.LOCAL,
            ollama=OllamaConfig(
                base_url="http://localhost:11434",
                planner_model="qwen2.5:7b-instruct",
                executor_model="qwen2.5:4b-instruct",
            ),
        )

        with patch("account_payable_demo.workflow.OpenAIProvider") as mock_provider:
            mock_instance = MagicMock()
            mock_provider.return_value = mock_instance

            create_sdk_provider(config, "executor")

            mock_provider.assert_called_once_with(
                model="qwen2.5:4b-instruct",
                base_url="http://localhost:11434/v1",
                api_key="ollama",
            )

    def test_create_deepinfra_provider(self):
        """Test creating DeepInfra provider."""
        config = DemoConfig(
            llm_mode=LLMMode.CLOUD,
            cloud_llm=CloudLLMConfig(
                planner_provider="deepinfra",
                planner_model="meta-llama/Llama-2-70b-chat-hf",
                executor_provider="deepinfra",
                executor_model="meta-llama/Llama-2-7b-chat-hf",
                deepinfra_api_key="test-deepinfra-key",
            ),
        )

        with patch("account_payable_demo.workflow.DeepInfraProvider") as mock_provider:
            mock_instance = MagicMock()
            mock_provider.return_value = mock_instance

            create_sdk_provider(config, "planner")

            mock_provider.assert_called_once_with(
                model="meta-llama/Llama-2-70b-chat-hf",
                api_key="test-deepinfra-key",
            )

    def test_unsupported_provider_raises_error(self):
        """Test that unsupported provider raises ValueError."""
        config = DemoConfig(
            llm_mode=LLMMode.CLOUD,
            cloud_llm=CloudLLMConfig(
                planner_provider="unsupported",
                planner_model="some-model",
                executor_provider="unsupported",
                executor_model="some-model",
            ),
        )

        with pytest.raises(ValueError, match="Unsupported provider"):
            create_sdk_provider(config, "planner")


class TestHelperFunctions:
    """Tests for helper functions (for testing purposes only)."""

    def test_build_predicate_spec(self):
        """Test building predicate spec dict."""
        spec = build_predicate_spec("exists", selector=".test-element")
        assert spec["predicate"] == "exists"
        assert ".test-element" in spec["args"]

    def test_build_demo_plan_step(self):
        """Test building demo plan step dict."""
        step = build_demo_plan_step(
            step_id=1,
            goal="Test goal",
            action="click",
        )
        assert step["id"] == 1
        assert step["goal"] == "Test goal"
        assert step["action"] == "CLICK"


class TestSDKIntegration:
    """Integration tests for SDK compatibility.

    These tests verify that the workflow uses correct SDK APIs.
    """

    def test_tracer_instantiation(self):
        """Test that Tracer can be instantiated correctly."""
        import tempfile
        import uuid

        from predicate import JsonlTraceSink, Tracer

        with tempfile.TemporaryDirectory() as tmpdir:
            trace_file = Path(tmpdir) / "test-trace.jsonl"
            run_id = str(uuid.uuid4())

            # This should not raise - verifies SDK API compatibility
            sink = JsonlTraceSink(trace_file)
            tracer = Tracer(run_id=run_id, sink=sink)

            assert tracer is not None

    def test_planner_executor_config_instantiation(self):
        """Test that PlannerExecutorConfig can be instantiated correctly."""
        from predicate.agents import PlannerExecutorConfig

        # This should not raise - verifies SDK API compatibility
        config = PlannerExecutorConfig(verbose=True)
        assert config is not None

    def test_planner_executor_agent_instantiation(self):
        """Test that PlannerExecutorAgent can be instantiated correctly."""
        import tempfile
        import uuid

        from predicate import JsonlTraceSink, Tracer
        from predicate.agents import PlannerExecutorAgent, PlannerExecutorConfig

        with tempfile.TemporaryDirectory() as tmpdir:
            trace_file = Path(tmpdir) / "test-trace.jsonl"
            run_id = str(uuid.uuid4())

            sink = JsonlTraceSink(trace_file)
            tracer = Tracer(run_id=run_id, sink=sink)
            config = PlannerExecutorConfig(verbose=False)

            # Mock providers
            mock_planner = MagicMock()
            mock_executor = MagicMock()

            # This should not raise - verifies SDK API compatibility
            agent = PlannerExecutorAgent(
                planner=mock_planner,
                executor=mock_executor,
                config=config,
                tracer=tracer,
            )

            assert agent is not None

    def test_automation_task_structure(self):
        """Test that AutomationTask matches SDK expectations."""
        from predicate.agents import TaskCategory

        # This should not raise - verifies SDK API compatibility
        task = AutomationTask(
            task_id="test-task",
            starting_url="https://example.com",
            task="Test task description",
            goal={"action": "test"},
            category=TaskCategory.FORM_FILL,
            max_steps=5,
        )

        assert task.task_id == "test-task"
        assert task.starting_url == "https://example.com"

    def test_predicate_types_available(self):
        """Test that verification predicate types are available."""
        from predicate import (
            all_of,
            any_of,
            element_count,
            exists,
            not_exists,
            url_contains,
        )

        # These should all be callable - verifies SDK exports
        assert callable(url_contains)
        assert callable(exists)
        assert callable(not_exists)
        assert callable(element_count)
        assert callable(all_of)
        assert callable(any_of)


class TestDemoStoryAlignment:
    """Tests verifying alignment with the finance demo story.

    The demo story has 4 beats:
    1. Normal action - Open invoice, compare fields, add note
    2. Mark Reconciled - Click appears to work but state doesn't change
    3. Release Payment - Risky action blocked by policy
    4. Route To Review - Safe fallback action succeeds
    """

    def test_beat_1_is_normal_workflow(self):
        """Beat 1 should be a standard successful workflow."""
        task = get_beat_1_task()
        # Standard form fill operation
        assert task.category == TaskCategory.FORM_FILL
        # Multiple steps expected (open, compare, add note)
        assert task.max_steps >= 5

    def test_beat_2_demonstrates_silent_failure(self):
        """Beat 2 should demonstrate 'clicked but state didn't change'."""
        task = get_beat_2_task()
        verification = get_beat_2_verification()

        # Task tries to mark as reconciled
        assert "reconciled" in task.task.lower()

        # Verification checks for status change
        # (will FAIL in demo, proving silent failure detection)
        assert len(verification) >= 1

    def test_beat_3_is_high_risk_transaction(self):
        """Beat 3 should be a high-risk action that gets blocked."""
        task = get_beat_3_task()

        # Marked as transaction (high risk)
        assert task.category == TaskCategory.TRANSACTION

        # Payment release is risky
        assert "payment" in task.task.lower()

    def test_beat_4_is_safe_fallback(self):
        """Beat 4 should be the safe alternative after block."""
        task = get_beat_4_task()

        # Form fill (safe action)
        assert task.category == TaskCategory.FORM_FILL

        # Routes to review instead of direct action
        assert "review" in task.task.lower()
