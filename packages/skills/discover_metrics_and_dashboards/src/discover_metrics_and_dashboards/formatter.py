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
            parts.append("## Metrics\n")  # blank line after heading
            for asset in discovery_result.ranked_metrics:
                parts.append(_format_metric_line(asset))

        if discovery_result.ranked_dashboards:
            parts.append("\n## Dashboards\n")  # blank lines around heading
            for asset in discovery_result.ranked_dashboards:
                parts.append(_format_dashboard_line(asset))

        # Join with double newlines so every item is its own paragraph block
        # for the chat markdown renderer — prevents heading blocks from swallowing items
        formatted = "\n\n".join(parts)
        logger.debug(
            "Formatted discovery result for run_id=%s: %d chars",
            result.run_id,
            len(formatted),
        )
        return formatted


def _human_name(name: str) -> str:
    """Convert snake_case or raw identifiers to a readable display name."""
    # If it already has spaces (e.g. Lightdash labels) leave it alone
    if " " in name:
        return name
    return name.replace("_", " ").strip()


def _format_metric_line(asset: RankedAsset) -> str:
    score_pct = f"{asset.relevance_score:.0%}"
    display = _human_name(asset.name)
    header = f"- **{display}** — {asset.reason} *(relevance: {score_pct})*"
    if asset.description:
        return f"{header}\n  {asset.description}"
    return header


def _format_dashboard_line(asset: RankedAsset) -> str:
    name_part = f"[{asset.name}]({asset.url})" if asset.url else asset.name
    header = f"- **{name_part}** — {asset.reason}"
    if asset.description:
        return f"{header}\n  {asset.description}"
    return header
