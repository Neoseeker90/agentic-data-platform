from __future__ import annotations

import logging

from contracts.context_pack import ContextPack, SourceAuthority
from contracts.validation import ValidationCheck, ValidationResult

from .models import BusinessQuestionPlan

logger = logging.getLogger(__name__)


class BusinessQuestionValidator:
    async def validate(
        self,
        plan: BusinessQuestionPlan,
        context: ContextPack,
    ) -> ValidationResult:
        checks: list[ValidationCheck] = []

        # Check 1: has_authoritative_source
        has_primary = any(s.authority == SourceAuthority.PRIMARY for s in context.sources)
        auth_severity = "error" if plan.identified_metrics else "warning"
        checks.append(
            ValidationCheck(
                check_name="has_authoritative_source",
                passed=has_primary,
                message=(None if has_primary else "No primary-authority source found in context."),
                severity=auth_severity,
            )
        )

        # Check 2: low_planning_confidence (warning only)
        confidence_ok = plan.planning_confidence >= 0.5
        checks.append(
            ValidationCheck(
                check_name="low_planning_confidence",
                passed=confidence_ok,
                message=(
                    None
                    if confidence_ok
                    else f"Planning confidence is low: {plan.planning_confidence:.2f}"
                ),
                severity="warning",
            )
        )

        # Check 3: unresolved_ambiguities (warning only)
        no_ambiguities = len(context.unresolved_ambiguities) == 0
        checks.append(
            ValidationCheck(
                check_name="unresolved_ambiguities",
                passed=no_ambiguities,
                message=(
                    None
                    if no_ambiguities
                    else f"Unresolved ambiguous terms: {context.unresolved_ambiguities}"
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
