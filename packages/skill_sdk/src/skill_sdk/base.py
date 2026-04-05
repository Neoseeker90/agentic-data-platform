from abc import ABC, abstractmethod

from contracts.context_pack import ContextPack
from contracts.execution import ExecutionResult
from contracts.plan import BasePlan
from contracts.run import Run
from contracts.validation import ValidationResult


class Skill(ABC):
    """Abstract base class for all platform skills.

    Each skill owns the full lifecycle for one type of request:
    plan -> build_context -> validate -> execute -> format_result.
    """

    name: str
    description: str
    risk_level: str  # "read_only" | "low_risk_write" | "high_risk_write"
    version: str = "1.0.0"

    @abstractmethod
    async def plan(self, request_text: str, run: Run, context: dict | None = None) -> BasePlan:
        """Interpret the request and produce a typed, validated plan.

        Must record a TokenCostRecord if an LLM call is made.
        """

    @abstractmethod
    async def build_context(
        self, plan: BasePlan, run: Run, context: dict | None = None
    ) -> ContextPack:
        """Retrieve all relevant context for this plan.

        Returns a ContextPack with labeled, prioritised sources.
        """

    @abstractmethod
    async def validate(self, plan: BasePlan, built_context: ContextPack) -> ValidationResult:
        """Structural and policy validation of the plan against the context.

        Returns ValidationResult with passed flag, checks list,
        and requires_approval flag.
        """

    @abstractmethod
    async def execute(self, plan: BasePlan, built_context: ContextPack) -> ExecutionResult:
        """Deterministic execution based on the validated plan and context.

        Execution must not perform freeform LLM calls that are not tightly
        constrained by a fixed output schema.
        """

    @abstractmethod
    async def format_result(self, result: ExecutionResult) -> str:
        """Format the execution result into a human-readable response.

        May call the LLM for formatting only — must record token costs.
        """

    def requires_approval(self, plan: BasePlan) -> bool:
        """Override to require human approval for specific plan shapes."""
        return self.risk_level == "high_risk_write"

    def required_permissions(self) -> list[str]:
        """Return permission strings this skill requires."""
        return []

    def supported_interfaces(self) -> list[str]:
        """Return list of interfaces this skill supports."""
        return ["web", "teams", "cursor", "cli", "api"]

    def on_before_execute(  # noqa: B027
        self, plan: BasePlan, built_context: ContextPack
    ) -> None:
        """Optional pre-execution hook."""

    def on_after_execute(  # noqa: B027
        self, result: ExecutionResult
    ) -> None:
        """Optional post-execution hook for cleanup or side effects."""
