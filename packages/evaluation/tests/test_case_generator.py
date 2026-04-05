from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from contracts.feedback import FeedbackFailureReason
from evaluation.case_generator import EvalCaseGenerator, derive_tags

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _fake_run(
    run_id: uuid.UUID | None = None,
    request_text: str = "What was our revenue?",
    selected_skill: str = "answer_business_question",
    state: str = "succeeded",
) -> MagicMock:
    run = MagicMock()
    run.run_id = run_id or uuid.uuid4()
    run.request_text = request_text
    run.selected_skill = selected_skill
    run.state = state
    return run


def _fake_feedback(
    run_id: uuid.UUID | None = None,
    score: int = 3,
    failure_reason: str | None = None,
) -> MagicMock:
    fb = MagicMock()
    fb.run_id = run_id or uuid.uuid4()
    fb.score = score
    fb.failure_reason = failure_reason
    return fb


def _fake_exec_result(formatted_response: str = "Revenue was $1M.") -> MagicMock:
    er = MagicMock()
    er.formatted_response = formatted_response
    return er


def _make_session_factory(run=None, feedback=None, exec_result=None):
    """Build a mock async session factory."""

    @asynccontextmanager
    async def _factory():
        session = AsyncMock()

        async def _execute(query):
            result = MagicMock()
            # Determine what to return based on context — we use call order
            return result

        # We need finer-grained control per call, so we use side_effect list
        run_scalar = MagicMock()
        run_scalar.scalar_one_or_none = MagicMock(return_value=run)

        fb_scalar = MagicMock()
        fb_scalar.scalar_one_or_none = MagicMock(return_value=feedback)

        er_scalar = MagicMock()
        er_scalar.scalar_one_or_none = MagicMock(return_value=exec_result)

        session.execute = AsyncMock(side_effect=[run_scalar, fb_scalar, er_scalar])
        yield session

    return _factory


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_from_run_returns_none_when_no_feedback():
    run_id = uuid.uuid4()
    run = _fake_run(run_id=run_id)
    factory = _make_session_factory(run=run, feedback=None, exec_result=None)
    generator = EvalCaseGenerator(factory)
    result = await generator.generate_from_run(run_id)
    assert result is None


@pytest.mark.asyncio
async def test_generate_from_run_builds_case():
    run_id = uuid.uuid4()
    run = _fake_run(
        run_id=run_id, request_text="Show revenue", selected_skill="answer_business_question"
    )
    feedback = _fake_feedback(run_id=run_id, score=2, failure_reason=None)
    exec_result = _fake_exec_result(formatted_response="Revenue is $500K.")
    factory = _make_session_factory(run=run, feedback=feedback, exec_result=exec_result)

    generator = EvalCaseGenerator(factory)
    case = await generator.generate_from_run(run_id)

    assert case is not None
    assert case.source_run_id == run_id
    assert case.request_text == "Show revenue"
    assert case.observed_skill == "answer_business_question"
    assert case.observed_response == "Revenue is $500K."
    assert case.feedback_score == 2
    assert case.created_by == "auto"


def test_derive_tags_includes_skill_name():
    run = _fake_run(selected_skill="explain_metric_definition")
    tags = derive_tags(run, feedback=None)
    assert "explain_metric_definition" in tags


def test_derive_tags_low_rated_adds_tag():
    run = _fake_run(selected_skill="answer_business_question")
    feedback = _fake_feedback(score=1, failure_reason=None)
    tags = derive_tags(run, feedback=feedback)
    assert "low_rated" in tags
    assert "has_feedback" in tags


def test_derive_tags_routing_reason():
    run = _fake_run(selected_skill="answer_business_question")
    feedback = _fake_feedback(score=2, failure_reason=FeedbackFailureReason.WRONG_SKILL_SELECTED)
    tags = derive_tags(run, feedback=feedback)
    assert "routing" in tags


def test_derive_tags_context_quality_reason():
    run = _fake_run(selected_skill="answer_business_question")
    feedback = _fake_feedback(score=2, failure_reason=FeedbackFailureReason.MISSING_CONTEXT)
    tags = derive_tags(run, feedback=feedback)
    assert "context_quality" in tags
