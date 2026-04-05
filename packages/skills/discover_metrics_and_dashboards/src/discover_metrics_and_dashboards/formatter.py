from __future__ import annotations

import logging

from contracts.execution import ExecutionResult

from .models import DiscoveryResult, RankedAsset

logger = logging.getLogger(__name__)

_NO_RESULTS_MESSAGE = (
    "No matching assets were found for your query. "
    "Try different search terms or browse available dashboards directly."
)


class DiscoveryFormatter:
    def format_result(self, result: ExecutionResult) -> str:
        discovery_result = DiscoveryResult.model_validate(result.output)

        if discovery_result.total_found == 0:
            logger.debug("Formatting empty discovery result for run_id=%s", result.run_id)
            return _NO_RESULTS_MESSAGE

        parts: list[str] = []

        if discovery_result.ranked_metrics:
            parts.append("## Metrics")
            for asset in discovery_result.ranked_metrics:
                parts.append(_format_metric_line(asset))

        if discovery_result.ranked_dashboards:
            if parts:
                parts.append("")
            parts.append("## Dashboards")
            for asset in discovery_result.ranked_dashboards:
                parts.append(_format_dashboard_line(asset))

        formatted = "\n".join(parts)
        logger.debug(
            "Formatted discovery result for run_id=%s: %d chars",
            result.run_id,
            len(formatted),
        )
        return formatted


def _format_metric_line(asset: RankedAsset) -> str:
    score_pct = f"{asset.relevance_score:.0%}"
    header = f"- **{asset.name}** — {asset.reason} *(relevance: {score_pct})*"
    if asset.description:
        return f"{header}\n  {asset.description}"
    return header


def _format_dashboard_line(asset: RankedAsset) -> str:
    if asset.url:
        name_part = f"[{asset.name}]({asset.url})"
    else:
        name_part = asset.name
    header = f"- **{name_part}** — {asset.reason}"
    if asset.description:
        return f"{header}\n  {asset.description}"
    return header
