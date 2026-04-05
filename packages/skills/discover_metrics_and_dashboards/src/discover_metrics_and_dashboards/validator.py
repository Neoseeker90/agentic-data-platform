from __future__ import annotations

import logging

from contracts.context_pack import ContextPack
from contracts.validation import ValidationCheck, ValidationResult

from .models import DiscoveryPlan

logger = logging.getLogger(__name__)


class DiscoveryValidator:
    async def validate(
        self,
        plan: DiscoveryPlan,
        context: ContextPack,
    ) -> ValidationResult:
        checks: list[ValidationCheck] = []

        # Check: has_candidates — warning only so empty results degrade gracefully
        has_candidates = len(context.sources) > 0
        checks.append(
            ValidationCheck(
                check_name="has_candidates",
                passed=has_candidates,
                message=(
                    None
                    if has_candidates
                    else "No candidate assets found for the given search terms."
                ),
                severity="warning",
            )
        )

        # Discovery skill always passes validation — graceful degradation on no results
        logger.info(
            "Validation for discovery plan_id=%s: has_candidates=%s",
            plan.plan_id,
            has_candidates,
        )

        return ValidationResult(
            run_id=plan.run_id,
            plan_id=plan.plan_id,
            passed=True,
            checks=checks,
            risk_level="low",
            requires_approval=False,
        )
