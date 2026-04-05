from __future__ import annotations

import logging
from collections import defaultdict
from uuid import UUID

from contracts.evaluation import EvaluationCase
from evaluation.dataset import EvalDataset
from evaluation.report import CaseResult, EvalReport, FailureCluster
from evaluation.scorers.base import BaseScorer, ScorerResult
from skill_sdk.registry import SkillRegistry

logger = logging.getLogger(__name__)


class EvalHarness:
    def __init__(
        self,
        registry: SkillRegistry,
        dataset: EvalDataset,
        scorers: list[BaseScorer],
        pass_threshold: float = 0.5,
    ) -> None:
        self._registry = registry
        self._dataset = dataset
        self._scorers = scorers
        self._pass_threshold = pass_threshold

    async def run(self, tags: list[str] | None = None) -> EvalReport:
        cases = await self._dataset.list_cases(tags=tags)

        case_results: list[CaseResult] = []
        for case in cases:
            result = await self.run_single(case)
            case_results.append(result)

        total = len(case_results)
        passed = sum(1 for cr in case_results if cr.passed)

        # Aggregate metrics: average per metric across all cases
        metric_totals: dict[str, list[float]] = defaultdict(list)
        for cr in case_results:
            for sr in cr.scorer_results:
                metric_totals[sr.metric].append(sr.value)

        metrics = {
            metric: sum(values) / len(values)
            for metric, values in metric_totals.items()
        }

        # Per-skill metrics
        skill_metric_totals: dict[str, dict[str, list[float]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for cr in case_results:
            skill_key = cr.actual_skill or cr.expected_skill or "unknown"
            for sr in cr.scorer_results:
                skill_metric_totals[skill_key][sr.metric].append(sr.value)

        per_skill_metrics: dict[str, dict[str, float]] = {
            skill: {
                metric: sum(values) / len(values)
                for metric, values in skill_data.items()
            }
            for skill, skill_data in skill_metric_totals.items()
        }

        # Failure clusters by dataset tag
        tag_total: dict[str, int] = defaultdict(int)
        tag_failed: dict[str, int] = defaultdict(int)
        tag_examples: dict[str, list[UUID]] = defaultdict(list)

        for case, cr in zip(cases, case_results):
            for tag in case.dataset_tags:
                tag_total[tag] += 1
                if not cr.passed:
                    tag_failed[tag] += 1
                    if len(tag_examples[tag]) < 3:
                        tag_examples[tag].append(cr.case_id)

        failure_clusters: list[FailureCluster] = [
            FailureCluster(
                tag=tag,
                count=tag_failed[tag],
                failure_rate=tag_failed[tag] / tag_total[tag] if tag_total[tag] > 0 else 0.0,
                example_case_ids=tag_examples[tag],
            )
            for tag in tag_failed
            if tag_failed[tag] > 0
        ]
        failure_clusters.sort(key=lambda c: c.failure_rate, reverse=True)

        return EvalReport(
            total_cases=total,
            passed_cases=passed,
            metrics=metrics,
            per_skill_metrics=per_skill_metrics,
            failure_clusters=failure_clusters,
            case_results=case_results,
        )

    async def run_single(self, case: EvaluationCase) -> CaseResult:
        actual_skill: str | None = case.observed_skill
        observed_response: str = case.observed_response or ""

        scorer_results: list[ScorerResult] = []
        error: str | None = None

        try:
            for scorer in self._scorers:
                result = scorer.score(
                    case,
                    actual_skill=actual_skill or "",
                    observed_response=observed_response,
                )
                scorer_results.append(result)
        except Exception as exc:
            logger.exception("Scorer error for case %s", case.case_id)
            error = str(exc)

        passed = bool(scorer_results) and all(
            r.value >= self._pass_threshold for r in scorer_results
        )

        return CaseResult(
            case_id=case.case_id,
            request_text=case.request_text,
            expected_skill=case.expected_skill,
            actual_skill=actual_skill,
            scorer_results=scorer_results,
            passed=passed,
            error=error,
        )
