from __future__ import annotations

from contracts.evaluation import EvaluationCase
from evaluation.scorers.base import BaseScorer, ScorerResult


class DiscoveryRecallScorer(BaseScorer):
    """Checks what fraction of expected_asset_refs appear in the observed response."""

    def score(
        self,
        case: EvaluationCase,
        actual_skill: str,
        observed_response: str,
    ) -> ScorerResult:
        if not case.expected_asset_refs:
            return ScorerResult(
                metric="discovery_recall",
                value=1.0,
                detail="no expected refs",
            )
        found = sum(
            1 for ref in case.expected_asset_refs if ref.lower() in observed_response.lower()
        )
        recall = found / len(case.expected_asset_refs)
        return ScorerResult(
            metric="discovery_recall",
            value=recall,
            detail=f"{found}/{len(case.expected_asset_refs)} refs found",
        )
