import pytest

from contracts.evaluation import EvaluationCase
from evaluation.scorers.discovery_scorer import DiscoveryRecallScorer
from evaluation.scorers.routing_scorer import RoutingScorer


def _make_case(**kwargs) -> EvaluationCase:
    defaults = {
        "request_text": "some request",
        "expected_skill": "skill_a",
        "expected_asset_refs": [],
    }
    defaults.update(kwargs)
    return EvaluationCase(**defaults)


class TestRoutingScorer:
    def test_routing_scorer_correct(self) -> None:
        scorer = RoutingScorer()
        case = _make_case(expected_skill="skill_a")
        result = scorer.score(case, actual_skill="skill_a", observed_response="")
        assert result.metric == "routing_accuracy"
        assert result.value == 1.0

    def test_routing_scorer_wrong(self) -> None:
        scorer = RoutingScorer()
        case = _make_case(expected_skill="skill_a")
        result = scorer.score(case, actual_skill="skill_b", observed_response="")
        assert result.metric == "routing_accuracy"
        assert result.value == 0.0
        assert "expected=skill_a" in result.detail
        assert "actual=skill_b" in result.detail

    def test_routing_scorer_no_expected(self) -> None:
        scorer = RoutingScorer()
        case = _make_case(expected_skill=None)
        result = scorer.score(case, actual_skill="skill_b", observed_response="")
        assert result.metric == "routing_accuracy"
        assert result.value == 1.0
        assert "skipped" in result.detail


class TestDiscoveryRecallScorer:
    def test_discovery_recall_full(self) -> None:
        scorer = DiscoveryRecallScorer()
        case = _make_case(expected_asset_refs=["revenue_dashboard", "gross_margin"])
        response = "Here is the revenue_dashboard and the gross_margin metric."
        result = scorer.score(case, actual_skill="discover_metrics", observed_response=response)
        assert result.metric == "discovery_recall"
        assert result.value == 1.0
        assert "2/2" in result.detail

    def test_discovery_recall_partial(self) -> None:
        scorer = DiscoveryRecallScorer()
        case = _make_case(expected_asset_refs=["revenue_dashboard", "gross_margin"])
        response = "Here is the revenue_dashboard."
        result = scorer.score(case, actual_skill="discover_metrics", observed_response=response)
        assert result.metric == "discovery_recall"
        assert result.value == pytest.approx(0.5)
        assert "1/2" in result.detail

    def test_discovery_recall_empty_refs(self) -> None:
        scorer = DiscoveryRecallScorer()
        case = _make_case(expected_asset_refs=[])
        result = scorer.score(case, actual_skill="discover_metrics", observed_response="anything")
        assert result.metric == "discovery_recall"
        assert result.value == 1.0
        assert "no expected refs" in result.detail
