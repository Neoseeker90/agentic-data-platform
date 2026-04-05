from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from contracts.evaluation import EvaluationCase
from evaluation.harness import EvalHarness
from evaluation.scorers.base import BaseScorer, ScorerResult

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_case(
    case_id: uuid.UUID | None = None,
    request_text: str = "What is revenue?",
    expected_skill: str | None = "answer_business_question",
    observed_skill: str | None = "answer_business_question",
    observed_response: str | None = "Revenue is $1M.",
    dataset_tags: list[str] | None = None,
) -> EvaluationCase:
    return EvaluationCase(
        case_id=case_id or uuid.uuid4(),
        request_text=request_text,
        expected_skill=expected_skill,
        observed_skill=observed_skill,
        observed_response=observed_response,
        dataset_tags=dataset_tags or ["answer_business_question"],
    )


class _FixedScorer(BaseScorer):
    def __init__(self, value: float, metric: str = "fixed_metric") -> None:
        self._value = value
        self._metric = metric

    def score(self, case, actual_skill, observed_response) -> ScorerResult:
        return ScorerResult(metric=self._metric, value=self._value)


def _make_dataset(cases: list[EvaluationCase]) -> MagicMock:
    dataset = MagicMock()
    dataset.list_cases = AsyncMock(return_value=cases)
    return dataset


def _make_registry() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_harness_run_produces_report():
    cases = [_make_case(), _make_case()]
    dataset = _make_dataset(cases)
    registry = _make_registry()
    scorer = _FixedScorer(value=1.0, metric="routing_accuracy")

    harness = EvalHarness(registry=registry, dataset=dataset, scorers=[scorer])
    report = await harness.run()

    assert report.total_cases == 2
    assert report.passed_cases == 2
    assert report.pass_rate == pytest.approx(1.0)
    assert "routing_accuracy" in report.metrics
    assert report.metrics["routing_accuracy"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_harness_run_single_scores_existing_response():
    case = _make_case(
        observed_skill="answer_business_question",
        observed_response="Revenue is $2M.",
    )
    dataset = _make_dataset([])
    registry = _make_registry()
    scorer = _FixedScorer(value=1.0, metric="routing_accuracy")

    harness = EvalHarness(registry=registry, dataset=dataset, scorers=[scorer])
    result = await harness.run_single(case)

    assert result.actual_skill == "answer_business_question"
    assert len(result.scorer_results) == 1
    assert result.scorer_results[0].value == 1.0


@pytest.mark.asyncio
async def test_pass_threshold_applied():
    case = _make_case()
    dataset = _make_dataset([case])
    registry = _make_registry()
    scorer = _FixedScorer(value=0.3, metric="routing_accuracy")

    harness = EvalHarness(registry=registry, dataset=dataset, scorers=[scorer], pass_threshold=0.5)
    result = await harness.run_single(case)

    assert result.passed is False


@pytest.mark.asyncio
async def test_harness_failure_clusters_by_tag():
    case_pass = _make_case(dataset_tags=["routing"])
    case_fail = _make_case(dataset_tags=["routing"])
    dataset = _make_dataset([case_pass, case_fail])
    registry = _make_registry()

    call_count = 0

    class _AlternatingScorer(BaseScorer):
        def score(self, case, actual_skill, observed_response) -> ScorerResult:
            nonlocal call_count
            value = 1.0 if call_count % 2 == 0 else 0.0
            call_count += 1
            return ScorerResult(metric="routing_accuracy", value=value)

    harness = EvalHarness(
        registry=registry,
        dataset=dataset,
        scorers=[_AlternatingScorer()],
        pass_threshold=0.5,
    )
    report = await harness.run()

    assert report.total_cases == 2
    assert report.passed_cases == 1
    assert len(report.failure_clusters) == 1
    assert report.failure_clusters[0].tag == "routing"
    assert report.failure_clusters[0].count == 1
