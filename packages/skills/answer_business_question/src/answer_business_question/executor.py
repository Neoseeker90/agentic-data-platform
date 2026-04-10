from __future__ import annotations

import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from contracts.context_pack import ContextPack, ContextSource
from contracts.execution import ExecutionResult
from skill_sdk.exceptions import ExecutionError
from skill_sdk.json_utils import parse_llm_json

from .models import BusinessQuestionPlan, BusinessQuestionResult

logger = logging.getLogger(__name__)

_PROMPT_NAME = "execute_question_v1"
_DEFAULT_MODEL_ID = "claude-3-5-sonnet-20241022"
_MAX_TOKENS = 4096
_CONTEXT_CHAR_BUDGET = 8000


def _serialize_context(sources: list[ContextSource]) -> str:
    """Serialize context sources into a structured string grouped by source_type."""
    by_type: dict[str, list[ContextSource]] = {}
    for source in sources:
        key = source.source_type.value
        by_type.setdefault(key, []).append(source)

    parts: list[str] = []
    total_chars = 0

    for source_type, group in by_type.items():
        header = f"### {source_type.upper().replace('_', ' ')}"
        parts.append(header)
        total_chars += len(header) + 1

        for source in group:
            line = (
                f"- [{source.authority.upper()}] {source.label} "
                f"(ref: {source.object_ref}): {source.snippet}"
            )
            if total_chars + len(line) > _CONTEXT_CHAR_BUDGET:
                parts.append("  ... (additional sources truncated)")
                return "\n".join(parts)
            parts.append(line)
            total_chars += len(line) + 1

    return "\n".join(parts)


class BusinessQuestionExecutor:
    def __init__(
        self,
        anthropic_client: Any,
        prompt_loader: Any,
        cost_recorder: Any | None = None,
        execution_model: str | None = None,
    ) -> None:
        self._client = anthropic_client
        self._model_id = execution_model or _DEFAULT_MODEL_ID
        self._prompt_loader = prompt_loader
        self._cost_recorder = cost_recorder

    async def execute(
        self,
        plan: BusinessQuestionPlan,
        context: ContextPack,
    ) -> ExecutionResult:
        context_text = _serialize_context(context.sources)

        prompt = self._prompt_loader.render(
            _PROMPT_NAME,
            question=plan.intent_summary or "See original request.",
            context_text=context_text,
        )

        logger.debug("Calling LLM for execution plan_id=%s", plan.plan_id)

        _t0 = time.monotonic()
        try:
            response = await self._client.messages.create(
                model=self._model_id,
                max_tokens=_MAX_TOKENS,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise ExecutionError(f"LLM call failed during execution: {exc}") from exc
        _latency_ms = int((time.monotonic() - _t0) * 1000)

        if self._cost_recorder is not None:
            await self._cost_recorder.record(
                run_id=plan.run_id,
                stage="execution",
                skill_name="answer_business_question",
                provider="bedrock",
                model_id=self._model_id,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                latency_ms=_latency_ms,
            )

        raw_text = response.content[0].text
        logger.debug("Executor LLM raw response: %s", raw_text)

        try:
            raw = parse_llm_json(raw_text)
        except json.JSONDecodeError as exc:
            raise ExecutionError(f"Executor LLM returned non-JSON output: {raw_text!r}") from exc

        try:
            result = BusinessQuestionResult(
                answer_text=raw.get("answer_text", ""),
                trusted_references=raw.get("trusted_references", []),
                confidence=float(raw.get("confidence", 0.5)),
                caveat=raw.get("caveat"),
                suggested_dashboards=raw.get("suggested_dashboards", []),
            )
        except Exception as exc:
            raise ExecutionError(f"Failed to construct BusinessQuestionResult: {exc}") from exc

        logger.info(
            "Executed plan_id=%s confidence=%.2f",
            plan.plan_id,
            result.confidence,
        )

        return ExecutionResult(
            run_id=plan.run_id,
            plan_id=plan.plan_id,
            success=True,
            output=result.model_dump(),
            formatted_response=None,
            executed_at=datetime.now(UTC),
        )
