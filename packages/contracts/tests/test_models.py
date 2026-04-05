"""Unit tests for all contract models."""

from decimal import Decimal
from uuid import uuid4

import pytest

from contracts.context_pack import ContextPack, ContextSource, SourceAuthority, SourceType
from contracts.cost import TokenCostRecord
from contracts.feedback import FeedbackFailureReason, FeedbackRecord, ImplicitSignal
from contracts.route import RouteDecision
from contracts.run import TERMINAL_STATES, Run, RunState
from contracts.validation import ValidationCheck, ValidationResult


class TestRunState:
    def test_terminal_states_are_final(self) -> None:
        assert RunState.SUCCEEDED in TERMINAL_STATES
        assert RunState.FAILED in TERMINAL_STATES
        assert RunState.CANCELLED in TERMINAL_STATES

    def test_non_terminal_states_not_in_terminal(self) -> None:
        assert RunState.CREATED not in TERMINAL_STATES
        assert RunState.EXECUTING not in TERMINAL_STATES


class TestRun:
    def test_defaults(self) -> None:
        run = Run(user_id="u1", interface="web", request_text="hello")
        assert run.state == RunState.CREATED
        assert run.selected_skill is None
        assert run.run_id is not None

    def test_serialise_roundtrip(self) -> None:
        run = Run(user_id="u1", interface="api", request_text="test")
        assert Run.model_validate(run.model_dump()) == run


class TestRouteDecision:
    def test_valid_decision(self) -> None:
        rd = RouteDecision(
            run_id=uuid4(),
            skill_name="answer_business_question",
            confidence=0.9,
        )
        assert rd.confidence == 0.9

    def test_confidence_bounds(self) -> None:
        with pytest.raises(Exception):  # noqa: B017
            RouteDecision(run_id=uuid4(), confidence=1.5)
        with pytest.raises(Exception):  # noqa: B017
            RouteDecision(run_id=uuid4(), confidence=-0.1)


class TestContextPack:
    def test_empty_pack(self) -> None:
        pack = ContextPack(run_id=uuid4(), plan_id=uuid4(), skill_name="test")
        assert pack.sources == []
        assert pack.unresolved_ambiguities == []

    def test_source_types(self) -> None:
        source = ContextSource(
            source_type=SourceType.LIGHTDASH_METRIC,
            authority=SourceAuthority.PRIMARY,
            object_ref="revenue",
            label="Revenue metric",
            snippet="Revenue is gross sales minus returns.",
        )
        assert source.authority == SourceAuthority.PRIMARY


class TestValidationResult:
    def test_errors_and_warnings_properties(self) -> None:
        result = ValidationResult(
            run_id=uuid4(),
            plan_id=uuid4(),
            passed=False,
            checks=[
                ValidationCheck(check_name="metric_exists", passed=False, severity="error"),
                ValidationCheck(check_name="ambiguous_term", passed=False, severity="warning"),
                ValidationCheck(check_name="source_available", passed=True),
            ],
        )
        assert len(result.errors) == 1
        assert len(result.warnings) == 1
        assert result.errors[0].check_name == "metric_exists"


class TestFeedbackRecord:
    def test_score_validation(self) -> None:
        with pytest.raises(Exception):  # noqa: B017
            FeedbackRecord(run_id=uuid4(), user_id="u1", score=6)
        with pytest.raises(Exception):  # noqa: B017
            FeedbackRecord(run_id=uuid4(), user_id="u1", score=0)

    def test_valid_score(self) -> None:
        fb = FeedbackRecord(run_id=uuid4(), user_id="u1", score=4, helpful=True)
        assert fb.score == 4

    def test_implicit_signals_list(self) -> None:
        fb = FeedbackRecord(
            run_id=uuid4(),
            user_id="u1",
            implicit_signals=[ImplicitSignal.CLICKED_DASHBOARD],
        )
        assert ImplicitSignal.CLICKED_DASHBOARD in fb.implicit_signals

    def test_failure_reason_enum(self) -> None:
        fb = FeedbackRecord(
            run_id=uuid4(),
            user_id="u1",
            failure_reason=FeedbackFailureReason.MISSING_CONTEXT,
        )
        assert fb.failure_reason == FeedbackFailureReason.MISSING_CONTEXT


class TestTokenCostRecord:
    def test_decimal_cost(self) -> None:
        record = TokenCostRecord(
            run_id=uuid4(),
            stage="routing",
            provider="anthropic",
            model_id="claude-3-haiku-20240307",
            prompt_tokens=500,
            completion_tokens=100,
            total_tokens=600,
            estimated_cost_usd=Decimal("0.000150"),
            latency_ms=320,
        )
        assert record.estimated_cost_usd == Decimal("0.000150")
