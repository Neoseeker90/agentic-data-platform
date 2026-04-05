from __future__ import annotations

from contracts.evaluation import EvaluationCase
from evaluation.scorers.base import BaseScorer, ScorerResult


class RoutingScorer(BaseScorer):
    def score(
        self,
        case: EvaluationCase,
        actual_skill: str,
        observed_response: str,
    ) -> ScorerResult:
        if case.expected_skill is None:
            return ScorerResult(
                metric="routing_accuracy",
                value=1.0,
                detail="no expected skill — skipped",
            )
        correct = actual_skill == case.expected_skill
        return ScorerResult(
            metric="routing_accuracy",
            value=1.0 if correct else 0.0,
            detail=f"expected={case.expected_skill} actual={actual_skill}",
        )
