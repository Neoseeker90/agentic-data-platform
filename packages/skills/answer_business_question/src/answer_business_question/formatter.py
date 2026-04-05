from __future__ import annotations

import logging

from contracts.execution import ExecutionResult

from .models import BusinessQuestionResult

logger = logging.getLogger(__name__)


class BusinessQuestionFormatter:
    def format_result(self, result: ExecutionResult) -> str:
        bq_result = BusinessQuestionResult.model_validate(result.output)

        parts: list[str] = [bq_result.answer_text]

        if bq_result.trusted_references:
            parts.append("")
            parts.append("---")
            parts.append("**References**")
            for ref in bq_result.trusted_references:
                link = f"[{ref.name}]({ref.url})" if ref.url else ref.name
                parts.append(f"- {link} — {ref.ref_type}")

        if bq_result.caveat:
            parts.append("")
            parts.append(f"> **Note:** {bq_result.caveat}")

        # Show unresolved ambiguities if present in result metadata
        unresolved = result.output.get("unresolved_ambiguities") or []
        if unresolved:
            parts.append("")
            parts.append(
                "> **Unresolved terms:** "
                + ", ".join(f"`{t}`" for t in unresolved)
                + " — these terms could not be matched to a known metric or definition."
            )

        formatted = "\n".join(parts)
        logger.debug("Formatted result for run_id=%s", result.run_id)
        return formatted
