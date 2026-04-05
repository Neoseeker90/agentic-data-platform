from __future__ import annotations

import logging
from typing import Any

from contracts.execution import ExecutionResult

from .models import DataQueryResult

logger = logging.getLogger(__name__)


def _rows_to_markdown_table(rows: list[dict], max_rows: int = 20) -> str:
    """Convert Lightdash query rows to a markdown table.

    Row format: {"field_id": {"value": {"raw": ..., "formatted": ...}}}
    Uses "formatted" value if available, falls back to "raw".
    """
    if not rows:
        return ""

    subset = rows[:max_rows]
    headers = list(rows[0].keys())

    def get_cell_value(cell: Any) -> str:
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
        return str(cell) if cell is not None else ""

    # Build header row
    lines: list[str] = []
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("| " + " | ".join("---" for _ in headers) + " |")

    for row in subset:
        cells = [get_cell_value(row.get(h)) for h in headers]
        lines.append("| " + " | ".join(cells) + " |")

    if len(rows) > max_rows:
        lines.append(f"\n_Showing {max_rows} of {len(rows)} rows._")

    return "\n".join(lines)


class DataQueryFormatter:
    def format_result(self, result: ExecutionResult) -> str:
        data = DataQueryResult.model_validate(result.output)

        if data.answer_type == "single_value":
            return data.answer_text or "(no data)"

        parts: list[str] = []

        if data.answer_text:
            parts.append(data.answer_text)

        if data.chart_url:

            def _label(fid: str) -> str:
                meta = data.fields_metadata.get(fid, {})
                return meta.get("label") or fid

            is_dashboard = "/dashboards/" in data.chart_url
            is_chart = "/charts/" in data.chart_url

            if is_dashboard:
                link_text = "View Dashboard in Lightdash →"
                note = "_Chart and dashboard have been created in the **Agent Answers** space._"
            elif is_chart:
                link_text = "View Chart in Lightdash →"
                note = "_Chart saved in the **Agent Answers** space._"
            else:
                link_text = "Open in Lightdash Explore →"
                field_lines: list[str] = []
                if data.dimensions:
                    dim_labels = ", ".join(f"`{_label(d)}`" for d in data.dimensions)
                    field_lines.append(f"- **Dimensions:** {dim_labels}")
                if data.metrics:
                    metric_labels = ", ".join(f"`{_label(m)}`" for m in data.metrics)
                    field_lines.append(f"- **Metrics:** {metric_labels}")
                note = "_Select these fields to reproduce the chart:_\n" + "\n".join(field_lines)

            parts.append(f"[{link_text}]({data.chart_url})\n{note}")

        if data.rows:
            parts.append("\n" + _rows_to_markdown_table(data.rows, max_rows=20))

        formatted = "\n\n".join(p for p in parts if p)
        logger.debug("Formatted result for run_id=%s", result.run_id)
        return formatted or "(no data)"
