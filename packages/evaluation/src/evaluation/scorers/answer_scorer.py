from __future__ import annotations

import asyncio
import logging
from typing import Any

from contracts.evaluation import EvaluationCase
from evaluation.scorers.base import BaseScorer, ScorerResult

logger = logging.getLogger(__name__)

_JUDGE_PROMPT = (
    "You are an evaluator. Given a user request and a system response, "
    "rate the response quality from 0.0 to 1.0 where 1.0 is perfect. "
    "Respond with ONLY a float number. "
    "Request: {request}. Response: {response}"
)


class AnswerQualityScorer(BaseScorer):
    """LLM-as-judge scorer. Uses a cheap model to rate answer quality.

    Optional — can be disabled in cost-sensitive runs by not including it in the harness.
    """

    def __init__(
        self,
        anthropic_client: Any,
        model_id: str = "claude-3-5-haiku-20241022",
    ) -> None:
        self._client = anthropic_client
        self._model_id = model_id

    def score(
        self,
        case: EvaluationCase,
        actual_skill: str,
        observed_response: str,
    ) -> ScorerResult:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.score_async(case, actual_skill, observed_response),
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.score_async(case, actual_skill, observed_response)
                )
        except Exception:
            logger.exception("AnswerQualityScorer failed for case %s", case.case_id)
            return ScorerResult(metric="answer_quality", value=0.0, detail="scorer error")

    async def score_async(
        self,
        case: EvaluationCase,
        actual_skill: str,
        observed_response: str,
    ) -> ScorerResult:
        if not observed_response:
            return ScorerResult(
                metric="answer_quality",
                value=0.0,
                detail="empty response",
            )

        prompt = _JUDGE_PROMPT.format(
            request=case.request_text,
            response=observed_response,
        )

        try:
            message = await self._client.messages.create(
                model=self._model_id,
                max_tokens=16,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            score = float(raw)
            score = max(0.0, min(1.0, score))
        except Exception:
            logger.exception("LLM judge call failed for case %s", case.case_id)
            return ScorerResult(metric="answer_quality", value=0.0, detail="llm call error")

        return ScorerResult(
            metric="answer_quality",
            value=score,
            detail=f"llm_judge={score:.3f}",
        )
