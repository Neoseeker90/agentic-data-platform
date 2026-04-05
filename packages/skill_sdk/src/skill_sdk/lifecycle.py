"""Run orchestrator — drives a Run through the full skill lifecycle."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from contracts.context_pack import ContextPack
from contracts.execution import ExecutionResult
from contracts.plan import BasePlan
from contracts.run import Run, RunState
from contracts.validation import ValidationResult
from skill_sdk.exceptions import ApprovalRequiredError, ClarificationNeeded, ValidationFailedError

if TYPE_CHECKING:
    from skill_sdk.base import Skill
    from skill_sdk.registry import SkillRegistry

logger = logging.getLogger(__name__)


class RunStore(Protocol):
    """Minimal interface the orchestrator needs from the run store."""

    async def update_state(
        self,
        run_id: str,
        state: RunState,
        **kwargs: object,
    ) -> Run: ...

    async def get(self, run_id: str) -> Run | None: ...


class RunAuditor(Protocol):
    """Minimal interface for audit record persistence."""

    async def record_plan(self, run: Run, plan: BasePlan) -> None: ...
    async def record_context_pack(self, run: Run, context_pack: ContextPack) -> None: ...
    async def record_validation_result(self, run: Run, result: ValidationResult) -> None: ...
    async def record_execution_result(self, run: Run, result: ExecutionResult) -> None: ...
    async def record_final_response(self, run: Run, formatted: str) -> None: ...


class RunOrchestrator:
    """Drives a Run through the full lifecycle using the matched skill.

    Inject RunStore and RunAuditor to decouple from persistence concerns.
    """

    def __init__(
        self,
        registry: SkillRegistry,
        run_store: RunStore,
        auditor: RunAuditor,
    ) -> None:
        self._registry = registry
        self._run_store = run_store
        self._auditor = auditor

    async def execute_run(self, run: Run) -> Run:
        """Execute the full lifecycle for a run that has already been routed.

        Plan, context pack, and execution result are threaded in-memory through
        each stage — no round-trip DB fetches needed between stages.
        """
        if not run.selected_skill:
            raise ValueError(f"Run {run.run_id} has no selected_skill — route first")

        skill = self._registry.get(run.selected_skill)

        try:
            run, plan = await self._run_plan(run, skill)
            run, context_pack = await self._run_build_context(run, skill, plan)
            run = await self._run_validate(run, skill, plan, context_pack)
            run, exec_result = await self._run_execute(run, skill, plan, context_pack)
            run = await self._run_format(run, skill, exec_result)
        except ClarificationNeeded as exc:
            await self._run_store.update_state(
                str(run.run_id),
                RunState.AWAITING_SKILL_CLARIFICATION,
                error_message=exc.question,
            )
            logger.info("Run %s needs skill clarification: %s", run.run_id, exc.question)
            return run
        except ApprovalRequiredError:
            run = await self._transition(run, RunState.AWAITING_APPROVAL)
            raise
        except Exception as exc:
            logger.exception("Run %s failed: %s", run.run_id, exc)
            run = await self._transition(
                run, RunState.FAILED, error_message=str(exc)
            )
            raise

        return run

    async def _run_plan(self, run: Run, skill: Skill) -> tuple[Run, BasePlan]:
        run = await self._transition(run, RunState.PLANNED)
        plan = await skill.plan(run.request_text, run)
        await self._auditor.record_plan(run, plan)
        return run, plan

    async def _run_build_context(
        self, run: Run, skill: Skill, plan: BasePlan
    ) -> tuple[Run, ContextPack]:
        run = await self._transition(run, RunState.CONTEXT_BUILT)
        context_pack = await skill.build_context(plan, run)
        await self._auditor.record_context_pack(run, context_pack)
        return run, context_pack

    async def _run_validate(
        self, run: Run, skill: Skill, plan: BasePlan, context_pack: ContextPack
    ) -> Run:
        validation = await skill.validate(plan, context_pack)
        await self._auditor.record_validation_result(run, validation)

        if not validation.passed:
            raise ValidationFailedError(
                f"Validation failed for run {run.run_id}",
                errors=[c.message or c.check_name for c in validation.errors],
            )

        run = await self._transition(run, RunState.VALIDATED)

        if validation.requires_approval or skill.requires_approval(plan):
            raise ApprovalRequiredError(str(run.run_id), str(plan.plan_id))

        return run

    async def _run_execute(
        self, run: Run, skill: Skill, plan: BasePlan, context_pack: ContextPack
    ) -> tuple[Run, ExecutionResult]:
        run = await self._transition(run, RunState.EXECUTING)
        skill.on_before_execute(plan, context_pack)
        result = await skill.execute(plan, context_pack)
        skill.on_after_execute(result)
        await self._auditor.record_execution_result(run, result)
        return run, result

    async def _run_format(
        self, run: Run, skill: Skill, exec_result: ExecutionResult
    ) -> Run:
        formatted = await skill.format_result(exec_result)
        await self._auditor.record_final_response(run, formatted)
        return await self._transition(run, RunState.SUCCEEDED)

    async def _transition(self, run: Run, new_state: RunState, **kwargs: object) -> Run:
        logger.info("Run %s: %s -> %s", run.run_id, run.state, new_state)
        return await self._run_store.update_state(str(run.run_id), new_state, **kwargs)
