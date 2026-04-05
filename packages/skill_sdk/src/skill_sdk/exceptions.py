class SkillNotFoundError(Exception):
    def __init__(self, skill_name: str) -> None:
        super().__init__(f"Skill '{skill_name}' is not registered")
        self.skill_name = skill_name


class PlanningError(Exception):
    """Raised when the LLM planner fails to produce a valid plan."""


class ContextBuildError(Exception):
    """Raised when context retrieval fails critically."""


class ValidationFailedError(Exception):
    """Raised when a plan fails validation and cannot proceed."""

    def __init__(self, message: str, errors: list[str] | None = None) -> None:
        super().__init__(message)
        self.errors = errors or []


class ApprovalRequiredError(Exception):
    """Raised to pause a run that requires human approval."""

    def __init__(self, run_id: str, plan_id: str) -> None:
        super().__init__(f"Run {run_id} requires approval before execution")
        self.run_id = run_id
        self.plan_id = plan_id


class ExecutionError(Exception):
    """Raised when skill execution fails."""


class ClarificationNeeded(Exception):
    """Raised by a skill planner when it needs more information before executing."""

    def __init__(self, question: str) -> None:
        super().__init__(question)
        self.question = question
