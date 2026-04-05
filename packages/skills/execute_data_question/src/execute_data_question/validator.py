from __future__ import annotations

import logging

from contracts.context_pack import ContextPack
from contracts.validation import ValidationCheck, ValidationResult
from lightdash_adapter.models import ExploreDetail

from .models import DataQueryPlan

logger = logging.getLogger(__name__)


def _extract_explore_detail(context: ContextPack) -> ExploreDetail | None:
    """Extract ExploreDetail from the first context source that has it."""
    for source in context.sources:
        raw = source.metadata.get("explore_detail")
        if raw is not None:
            try:
                return ExploreDetail.model_validate(raw)
            except Exception as exc:
                logger.warning("Failed to parse explore_detail from context source: %s", exc)
    return None


class DataQueryValidator:
    async def validate(
        self,
        plan: DataQueryPlan,
        context: ContextPack,
    ) -> ValidationResult:
        checks: list[ValidationCheck] = []

        # Check 1: has_explore — explore_name must be non-empty
        has_explore = bool(plan.explore_name)
        checks.append(
            ValidationCheck(
                check_name="has_explore",
                passed=has_explore,
                message=(
                    None
                    if has_explore
                    else "No explore name was identified in the plan. Cannot execute query."
                ),
                severity="error",
            )
        )

        # Check 2: has_metrics — at least one metric required
        has_metrics = len(plan.metrics) > 0
        checks.append(
            ValidationCheck(
                check_name="has_metrics",
                passed=has_metrics,
                message=(
                    None
                    if has_metrics
                    else "Plan contains no metrics. At least one metric is required to run a query."
                ),
                severity="error",
            )
        )

        # Check 3: fields_exist — all dimension/metric IDs exist in the explore detail
        explore_detail = _extract_explore_detail(context)

        if explore_detail is not None:
            valid_field_ids = {field.field_id for field in explore_detail.fields}
            metric_field_ids = {
                f.field_id for f in explore_detail.fields if f.field_type == "metric"
            }
            dimension_field_ids = {
                f.field_id for f in explore_detail.fields if f.field_type == "dimension"
            }

            all_requested = set(plan.dimensions) | set(plan.metrics)
            missing_fields = all_requested - valid_field_ids
            fields_exist = len(missing_fields) == 0
            checks.append(
                ValidationCheck(
                    check_name="fields_exist",
                    passed=fields_exist,
                    message=(
                        None
                        if fields_exist
                        else (
                            f"The following field IDs do not exist in explore "
                            f"'{plan.explore_name}': {sorted(missing_fields)}. "
                            "Only use field IDs that appear in the catalogue."
                        )
                    ),
                    severity="error",
                )
            )

            # Check 3b: correct_field_types — metrics must be metric fields, not dimensions
            wrong_type_metrics = set(plan.metrics) & dimension_field_ids
            wrong_type_dims = set(plan.dimensions) & metric_field_ids
            correct_types = not wrong_type_metrics and not wrong_type_dims
            if not correct_types:
                msg_parts = []
                if wrong_type_metrics:
                    msg_parts.append(
                        f"Fields used as metrics but are actually dimensions: {sorted(wrong_type_metrics)}. "
                        "Use only METRIC field IDs in the 'metrics' array."
                    )
                if wrong_type_dims:
                    msg_parts.append(
                        f"Fields used as dimensions but are actually metrics: {sorted(wrong_type_dims)}."
                    )
            checks.append(
                ValidationCheck(
                    check_name="correct_field_types",
                    passed=correct_types,
                    message=None if correct_types else " ".join(msg_parts),
                    severity="error",
                )
            )
        else:
            # No explore detail available — skip check with a warning
            logger.warning(
                "No explore_detail in context for plan_id=%s — skipping fields_exist check",
                plan.plan_id,
            )
            checks.append(
                ValidationCheck(
                    check_name="fields_exist",
                    passed=True,
                    message="Explore detail not available in context; field existence check skipped.",
                    severity="warning",
                )
            )

        # Check 4: reasonable_limit — warn if limit > 500
        reasonable_limit = plan.limit <= 500
        checks.append(
            ValidationCheck(
                check_name="reasonable_limit",
                passed=reasonable_limit,
                message=(
                    None
                    if reasonable_limit
                    else (
                        f"Query limit is {plan.limit}, which exceeds the recommended maximum of 500. "
                        "Large result sets may be slow or incomplete."
                    )
                ),
                severity="warning",
            )
        )

        # Check 5: low_planning_confidence — warn if planning_confidence < 0.5
        high_confidence = plan.planning_confidence >= 0.5
        checks.append(
            ValidationCheck(
                check_name="low_planning_confidence",
                passed=high_confidence,
                message=(
                    None
                    if high_confidence
                    else (
                        f"Planning confidence is low ({plan.planning_confidence:.2f}). "
                        "The query plan may not accurately reflect the user's intent."
                    )
                ),
                severity="warning",
            )
        )

        # Overall passed = no error-severity checks failed
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
