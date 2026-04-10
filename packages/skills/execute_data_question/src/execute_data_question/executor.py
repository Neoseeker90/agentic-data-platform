from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import UTC, datetime
from typing import Any

from contracts.context_pack import ContextPack
from contracts.execution import ExecutionResult
from lightdash_adapter.chart_uploader import ChartUploader
from lightdash_adapter.client import LightdashClient
from skill_sdk.exceptions import ExecutionError

from .models import DataQueryPlan, DataQueryResult

logger = logging.getLogger(__name__)

_PROMPT_NAME = "summarize_data_v1"


def _convert_filters(filters: dict) -> dict:
    """Convert planner's simplified filter format to the Lightdash and-array format.

    Planner produces:
      {"dimensions": {"field_id": {"values": [{"operator": "X", "values": [...]}]}}}

    Lightdash runQuery requires:
      {"dimensions": {"and": [{"id": "uuid", "target": {"fieldId": "...", "tableName": "..."}, "operator": "X", "values": [...]}]}}
    """
    import uuid as _uuid

    if not filters:
        return {}

    result: dict = {}

    for filter_group in ("dimensions", "metrics"):
        group = filters.get(filter_group)
        if not group:
            continue

        # Already in and-array format — pass through
        if "and" in group:
            result[filter_group] = group
            continue

        and_clauses = []
        for field_id, field_filter in group.items():
            table_name = field_id.rsplit("_", 1)[0] if "_" in field_id else field_id
            # field_filter may be {"values": [{operator, values}, ...]} or a single clause
            value_list = field_filter.get("values", [])
            if not value_list:
                continue
            for clause in value_list:
                if not isinstance(clause, dict) or "operator" not in clause:
                    continue
                and_clauses.append(
                    {
                        "id": str(_uuid.uuid4())[:8],
                        "target": {"fieldId": field_id, "tableName": table_name},
                        "operator": clause["operator"],
                        "values": clause.get("values", []),
                        **({"settings": clause["settings"]} if "settings" in clause else {}),
                    }
                )

        if and_clauses:
            result[filter_group] = {"and": and_clauses}

    return result


_DEFAULT_MODEL_ID = "claude-3-haiku-20240307"
_MAX_TOKENS = 1024
_MAX_PREVIEW_ROWS = 20


def _format_row_value(cell: Any) -> str:
    """Extract the best display value from a Lightdash row cell."""
    if isinstance(cell, dict):
        value = cell.get("value", {})
        if isinstance(value, dict):
            formatted = value.get("formatted")
            if formatted is not None:
                return str(formatted)
            raw = value.get("raw")
            if raw is not None:
                return str(raw)
        return str(value)
    return str(cell)


def _rows_to_preview(rows: list[dict], max_rows: int = _MAX_PREVIEW_ROWS) -> str:
    """Convert Lightdash query rows to a human-readable text preview."""
    if not rows:
        return "(no data)"
    subset = rows[:max_rows]
    headers = list(rows[0].keys())
    lines: list[str] = [" | ".join(headers)]
    lines.append("-" * len(lines[0]))
    for row in subset:
        cells = [_format_row_value(row.get(h)) for h in headers]
        lines.append(" | ".join(cells))
    if len(rows) > max_rows:
        lines.append(f"... ({len(rows) - max_rows} more rows)")
    return "\n".join(lines)


class DataQueryExecutor:
    def __init__(
        self,
        anthropic_client: Any,
        prompt_loader: Any,
        lightdash_client: LightdashClient,
        cost_recorder: Any | None = None,
        execution_model: str | None = None,
        chart_uploader: ChartUploader | None = None,
    ) -> None:
        self._client = anthropic_client
        self._model_id = execution_model or _DEFAULT_MODEL_ID
        self._prompt_loader = prompt_loader
        self._lightdash_client = lightdash_client
        self._cost_recorder = cost_recorder
        self._chart_uploader = chart_uploader

    async def execute(
        self,
        plan: DataQueryPlan,
        context: ContextPack,
    ) -> ExecutionResult:
        # Step 1: Run query via lightdash_client
        lightdash_filters = _convert_filters(plan.filters)
        logger.debug("Converted filters: %s", lightdash_filters)
        try:
            query_result = await self._lightdash_client.run_query(
                explore_name=plan.explore_name,
                dimensions=plan.dimensions,
                metrics=plan.metrics,
                filters=lightdash_filters,
                sorts=plan.sorts,
                limit=plan.limit,
            )
        except Exception as exc:
            msg = str(exc) or type(exc).__name__
            raise ExecutionError(f"Query execution failed: {msg}") from exc

        rows = query_result.rows
        row_count = query_result.row_count

        answer_text = ""
        chart_url: str | None = None
        chart_uuid: str | None = None

        # Step 2: Handle single_value answer type
        if plan.answer_type == "single_value" and rows and plan.metrics:
            first_metric = plan.metrics[0]
            first_row = rows[0]
            cell = first_row.get(first_metric, {})
            formatted_value = _format_row_value(cell)
            # Use the metric label from context if available, else field_id
            metric_label = first_metric
            for source in context.sources:
                if source.metadata.get("field_id") == first_metric:
                    metric_label = source.label
                    break
            answer_text = f"{metric_label}: {formatted_value}"
            logger.debug("Single value answer: %s", answer_text)

        # Step 3: For chart — always create a dashboard + chart via lightdash CLI.
        # For table — just create a chart (no dashboard container needed).
        if plan.answer_type in ("chart", "table"):
            if self._chart_uploader is not None:
                try:
                    if plan.answer_type == "chart":
                        _, chart_url = await asyncio.get_event_loop().run_in_executor(
                            None, self._chart_uploader.upload_dashboard_with_chart, plan
                        )
                    else:
                        _, chart_url = await asyncio.get_event_loop().run_in_executor(
                            None, self._chart_uploader.upload_chart, plan
                        )
                    logger.info("Created Lightdash chart/dashboard at %s", chart_url)
                except Exception as exc:
                    logger.warning("Chart upload failed, falling back to explore URL: %s", exc)
                    chart_url = self._lightdash_client.build_explore_url(
                        plan.explore_name, plan.dimensions, plan.metrics
                    )
            else:
                chart_url = self._lightdash_client.build_explore_url(
                    plan.explore_name, plan.dimensions, plan.metrics
                )
            logger.info("Chart URL: %s", chart_url)

        # Step 4: Build data preview string
        data_preview = _rows_to_preview(rows, max_rows=_MAX_PREVIEW_ROWS)

        # Step 5: Call LLM with summarize prompt (skip if single_value and already have answer_text)
        if not (plan.answer_type == "single_value" and answer_text):
            prompt = self._prompt_loader.render(
                _PROMPT_NAME,
                question=plan.intent_summary or "What does this data show?",
                answer_type=plan.answer_type,
                data_preview=data_preview,
            )

            logger.debug("Calling LLM for summarization plan_id=%s", plan.plan_id)

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
                    skill_name="execute_data_question",
                    provider="bedrock",
                    model_id=self._model_id,
                    prompt_tokens=response.usage.input_tokens,
                    completion_tokens=response.usage.output_tokens,
                    latency_ms=_latency_ms,
                )

            raw_text = response.content[0].text
            logger.debug("Executor LLM raw response: %s", raw_text)

            cleaned = raw_text.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

            try:
                raw = json.loads(cleaned)
            except json.JSONDecodeError as exc:
                raise ExecutionError(
                    f"Executor LLM returned non-JSON output: {raw_text!r}"
                ) from exc

            answer_text = raw.get("answer_text", "")
            llm_confidence = raw.get("confidence", 1.0)
        else:
            llm_confidence = 1.0

        # Step 6: Construct DataQueryResult and return ExecutionResult
        # Build field label lookup from query_result.fields (Lightdash returns metadata)
        fields_metadata = {
            fid: {
                "label": fmeta.get("label", fid),
                "field_type": fmeta.get("fieldType", ""),
            }
            for fid, fmeta in query_result.fields.items()
        }
        try:
            data_result = DataQueryResult(
                answer_text=answer_text,
                rows=rows,
                row_count=row_count,
                chart_url=chart_url,
                chart_uuid=chart_uuid,
                answer_type=plan.answer_type,
                confidence=llm_confidence,
                explore_name=plan.explore_name,
                dimensions=plan.dimensions,
                metrics=plan.metrics,
                fields_metadata=fields_metadata,
            )
        except Exception as exc:
            raise ExecutionError(f"Failed to construct DataQueryResult: {exc}") from exc

        logger.info(
            "Executed plan_id=%s rows=%d answer_type=%s chart=%s",
            plan.plan_id,
            row_count,
            plan.answer_type,
            chart_uuid or "none",
        )

        return ExecutionResult(
            run_id=plan.run_id,
            plan_id=plan.plan_id,
            success=True,
            output=data_result.model_dump(),
            formatted_response=None,
            executed_at=datetime.now(UTC),
        )
