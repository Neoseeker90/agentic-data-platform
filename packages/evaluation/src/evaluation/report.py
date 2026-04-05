from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from evaluation.scorers.base import ScorerResult


@dataclass
class CaseResult:
    case_id: UUID
    request_text: str
    expected_skill: str | None
    actual_skill: str | None
    scorer_results: list[ScorerResult]
    passed: bool
    error: str | None = None


@dataclass
class FailureCluster:
    tag: str
    count: int
    failure_rate: float
    example_case_ids: list[UUID]


@dataclass
class EvalReport:
    report_id: UUID = field(default_factory=uuid4)
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    total_cases: int = 0
    passed_cases: int = 0
    metrics: dict[str, float] = field(default_factory=dict)
    per_skill_metrics: dict[str, dict[str, float]] = field(default_factory=dict)
    failure_clusters: list[FailureCluster] = field(default_factory=list)
    case_results: list[CaseResult] = field(default_factory=list)

    @property
    def pass_rate(self) -> float:
        return self.passed_cases / self.total_cases if self.total_cases > 0 else 0.0


class EvalReportWriter:
    def write_markdown(self, report: EvalReport, path: Path) -> None:
        lines: list[str] = []
        lines.append(f"# Eval Report {report.report_id}")
        lines.append(
            f"Evaluated: {report.evaluated_at.isoformat()}  "
            f"Total: {report.total_cases}  "
            f"Pass rate: {report.pass_rate:.0%}"
        )
        lines.append("")

        lines.append("## Metrics")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("| --- | --- |")
        for metric, value in sorted(report.metrics.items()):
            lines.append(f"| {metric} | {value:.4f} |")
        lines.append("")

        lines.append("## Per-skill Metrics")
        lines.append("")
        if report.per_skill_metrics:
            all_metrics = sorted(
                {m for skill_data in report.per_skill_metrics.values() for m in skill_data}
            )
            header = "| Skill | " + " | ".join(all_metrics) + " |"
            separator = "| --- | " + " | ".join(["---"] * len(all_metrics)) + " |"
            lines.append(header)
            lines.append(separator)
            for skill, skill_data in sorted(report.per_skill_metrics.items()):
                row_values = [f"{skill_data.get(m, float('nan')):.4f}" for m in all_metrics]
                lines.append(f"| {skill} | " + " | ".join(row_values) + " |")
        else:
            lines.append("_No per-skill metrics available._")
        lines.append("")

        lines.append("## Failure Clusters")
        lines.append("")
        if report.failure_clusters:
            lines.append("| Tag | Count | Failure Rate |")
            lines.append("| --- | --- | --- |")
            for cluster in report.failure_clusters:
                lines.append(f"| {cluster.tag} | {cluster.count} | {cluster.failure_rate:.0%} |")
        else:
            lines.append("_No failure clusters._")
        lines.append("")

        lines.append("## Failed Cases")
        lines.append("")
        failed = [cr for cr in report.case_results if not cr.passed]
        if failed:
            for cr in failed:
                lines.append(f"- **{cr.case_id}**: {cr.request_text}")
                for sr in cr.scorer_results:
                    if sr.value < 1.0:
                        lines.append(f"  - `{sr.metric}={sr.value:.3f}` {sr.detail}")
                if cr.error:
                    lines.append(f"  - error: {cr.error}")
        else:
            lines.append("_All cases passed._")
        lines.append("")

        path.write_text("\n".join(lines), encoding="utf-8")

    def write_json(self, report: EvalReport, path: Path) -> None:
        def _default(obj: object) -> str:
            if isinstance(obj, UUID):
                return str(obj)
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")

        raw = dataclasses.asdict(report)
        path.write_text(json.dumps(raw, default=_default, indent=2), encoding="utf-8")
