from __future__ import annotations

import logging

from contracts.context_pack import ContextPack, SourceAuthority
from contracts.validation import ValidationCheck, ValidationResult

from .models import ExplainMetricPlan

logger = logging.getLogger(__name__)


class ExplainMetricValidator:
    async def validate(
        self,
        plan: ExplainMetricPlan,
        context: ContextPack,
    ) -> ValidationResult:
        checks: list[ValidationCheck] = []

        # Check 1: metric_found — hard fail if no sources at all
        no_sources = len(context.sources) == 0
        has_primary = any(s.authority == SourceAuthority.PRIMARY for s in context.sources)

        checks.append(
            ValidationCheck(
                check_name="metric_found",
                passed=not no_sources,
                message=(
                    None
                    if not no_sources
                    else (
                        f"Metric '{plan.normalized_metric_name}' was not found in any "
                        "authoritative source."
                    )
                ),
                severity="error",
            )
        )

        # Check 2: has_primary_definition — warning only
        checks.append(
            ValidationCheck(
                check_name="has_primary_definition",
                passed=has_primary,
                message=(
                    None
                    if has_primary
                    else (
                        "No primary-authority definition found. Definition may be incomplete "
                        "or based on secondary/supporting sources only."
                    )
                ),
                severity="warning",
            )
        )

        # Overall passed = no error-severity failures
        overall_passed = all(c.passed or c.severity != "error" for c in checks)

        logger.info(
            "Validation for plan_id=%s: passed=%s checks=%d",
            plan.plan_id,
            overall_passed,
            len(checks),
        )

        return ValidationResult(
            run_id=plan.run_id,
            plan_id=plan.plan_id,
            passed=overall_passed,
            checks=checks,
            risk_level="low",
            requires_approval=False,
        )
