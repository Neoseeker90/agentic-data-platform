from __future__ import annotations

import logging

from contracts.execution import ExecutionResult

from .models import MetricDefinitionResult

logger = logging.getLogger(__name__)


class ExplainMetricFormatter:
    def format_result(self, result: ExecutionResult) -> str:
        metric = MetricDefinitionResult.model_validate(result.output)

        parts: list[str] = []

        parts.append(f"## {metric.display_name}")
        parts.append("")
        parts.append(f"**Definition:** {metric.definition}")
        parts.append("")
        parts.append(f"**Business Meaning:** {metric.business_meaning}")
        parts.append("")
        parts.append(
            f"**Data Sources:** {', '.join(metric.data_sources) if metric.data_sources else '—'}"
        )

        if metric.caveats:
            parts.append("")
            parts.append("**Caveats:**")
            for caveat in metric.caveats:
                parts.append(f"- {caveat}")

        parts.append("")
        parts.append(
            f"**Related Dashboards:** "
            f"{', '.join(metric.related_dashboards) if metric.related_dashboards else '—'}"
        )

        if not metric.is_definition_complete:
            parts.append("")
            parts.append(
                "> ⚠️ **Incomplete definition**: This metric's definition could not be fully "
                "resolved from available sources."
            )

        if metric.conflicting_definitions:
            parts.append("")
            parts.append("> ⚠️ **Conflicting definitions detected:**")
            for conflict in metric.conflicting_definitions:
                parts.append(f"> - {conflict}")

        formatted = "\n".join(parts)
        logger.debug("Formatted result for run_id=%s", result.run_id)
        return formatted
