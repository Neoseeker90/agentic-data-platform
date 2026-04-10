import json
import logging
import time
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from contracts.route import RouteDecision
from contracts.run import Run
from router.config import RouterConfig
from router.exceptions import ClassificationError, NoSkillsRegisteredError
from router.prompt import PromptLoader
from skill_sdk.registry import SkillRegistry

logger = logging.getLogger(__name__)


class Router:
    """LLM-based request classifier that maps a user Run to a RouteDecision."""

    def __init__(
        self,
        registry: SkillRegistry,
        anthropic_client: Any,  # AsyncAnthropic or AsyncAnthropicBedrock
        prompt_loader: PromptLoader,
        config: RouterConfig | None = None,
        cost_recorder: Any | None = None,
    ) -> None:
        self._registry = registry
        self._client = anthropic_client
        self._prompt_loader = prompt_loader
        self.config = config or RouterConfig()
        self._cost_recorder = cost_recorder

    async def route(self, run: Run) -> RouteDecision:
        """Classify run.request_text and return a RouteDecision."""
        skills = self._registry.list_skills()
        if not skills:
            raise NoSkillsRegisteredError("Cannot route request: no skills are registered.")

        skills_list = "\n".join(
            f"- {s['name']} (v{s['version']}, risk={s['risk_level']}): {s['description']}"
            for s in skills
        )

        prompt = self._prompt_loader.render(
            self.config.prompt_name,
            skills_list=skills_list,
            request_text=run.request_text,
        )

        logger.debug("Calling LLM for run_id=%s", run.run_id)
        raw = await self._call_llm(prompt, run_id=run.run_id)

        decision = self._build_route_decision(run.run_id, raw)
        logger.info(
            "Routed run_id=%s to skill=%s confidence=%.2f",
            run.run_id,
            decision.skill_name,
            decision.confidence,
        )
        return decision

    async def _call_llm(self, prompt: str, run_id: UUID | None = None) -> dict:
        """Send the prompt to Anthropic and parse the JSON response."""
        _t0 = time.monotonic()
        response = await self._client.messages.create(
            model=self.config.model_id,
            max_tokens=self.config.max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        _latency_ms = int((time.monotonic() - _t0) * 1000)

        if self._cost_recorder is not None and run_id is not None:
            await self._cost_recorder.record(
                run_id=run_id,
                stage="routing",
                skill_name=None,
                provider="bedrock",
                model_id=self.config.model_id,
                prompt_tokens=response.usage.input_tokens,
                completion_tokens=response.usage.output_tokens,
                latency_ms=_latency_ms,
            )

        raw_text = response.content[0].text
        logger.debug("LLM raw response: %s", raw_text)

        try:
            return json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise ClassificationError(f"LLM returned non-JSON output: {raw_text!r}") from exc

    def _build_route_decision(self, run_id: UUID, raw: dict) -> RouteDecision:
        """Apply confidence thresholds and construct a RouteDecision."""
        confidence: float = float(raw.get("confidence", 0.0))
        requires_clarification: bool = bool(raw.get("requires_clarification", False))
        candidate_skills: list[str] = list(raw.get("candidate_skills") or [])

        # Force clarification when confidence is below the lower threshold.
        if confidence < self.config.clarification_threshold:
            requires_clarification = True

        # In the medium band, ensure candidate_skills is populated.
        if (
            self.config.clarification_threshold <= confidence < self.config.confidence_threshold
            and not candidate_skills
            and raw.get("skill_name")
        ):
            candidate_skills = [raw["skill_name"]]

        skill_name: str | None = None if requires_clarification else raw.get("skill_name")

        return RouteDecision(
            run_id=run_id,
            skill_name=skill_name,
            confidence=confidence,
            rationale=raw.get("rationale"),
            requires_clarification=requires_clarification,
            clarification_message=raw.get("clarification_message"),
            candidate_skills=candidate_skills,
            prompt_version_id=self._prompt_loader.get_version_id(self.config.prompt_name),
            model_id=self.config.model_id,
            decided_at=datetime.now(UTC),
        )
