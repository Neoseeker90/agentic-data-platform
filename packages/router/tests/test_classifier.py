"""Tests for the Router classifier."""

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from contracts.run import Run
from router import PromptLoader, Router, RouterConfig
from router.exceptions import ClassificationError, NoSkillsRegisteredError
from skill_sdk.registry import SkillRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_llm_response(payload: dict) -> MagicMock:
    """Wrap a dict as a fake Anthropic messages.create response."""
    content_block = MagicMock()
    content_block.text = json.dumps(payload)
    response = MagicMock()
    response.content = [content_block]
    return response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_registry() -> SkillRegistry:
    registry = SkillRegistry()
    skill = MagicMock()
    skill.name = "answer_business_question"
    skill.description = "Answer business questions using metrics and KPIs."
    skill.risk_level = "read_only"
    skill.version = "1.0.0"
    registry.register(skill)
    return registry


@pytest.fixture()
def mock_anthropic() -> MagicMock:
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock()
    return client


@pytest.fixture()
def sample_run() -> Run:
    return Run(
        user_id="u1",
        interface="api",
        request_text="What was revenue last quarter?",
    )


@pytest.fixture()
def prompt_loader() -> PromptLoader:
    """PromptLoader pointing at the real prompts directory."""
    prompts_dir = Path(__file__).parent.parent / "prompts"
    return PromptLoader(prompts_dir=prompts_dir)


@pytest.fixture()
def router(
    mock_registry: SkillRegistry, mock_anthropic: MagicMock, prompt_loader: PromptLoader
) -> Router:
    return Router(
        registry=mock_registry,
        anthropic_client=mock_anthropic,
        prompt_loader=prompt_loader,
        config=RouterConfig(),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routes_high_confidence_request(
    router: Router,
    mock_anthropic: MagicMock,
    sample_run: Run,
) -> None:
    mock_anthropic.messages.create.return_value = _make_llm_response(
        {
            "skill_name": "answer_business_question",
            "confidence": 0.95,
            "rationale": "User is asking for a revenue figure, which is a business metric.",
            "requires_clarification": False,
            "clarification_message": None,
            "candidate_skills": [],
        }
    )

    decision = await router.route(sample_run)

    assert decision.skill_name == "answer_business_question"
    assert decision.requires_clarification is False
    assert decision.confidence == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_requires_clarification_when_low_confidence(
    router: Router,
    mock_anthropic: MagicMock,
    sample_run: Run,
) -> None:
    mock_anthropic.messages.create.return_value = _make_llm_response(
        {
            "skill_name": "answer_business_question",
            "confidence": 0.3,
            "rationale": "Request is ambiguous.",
            "requires_clarification": False,
            "clarification_message": None,
            "candidate_skills": [],
        }
    )

    decision = await router.route(sample_run)

    assert decision.requires_clarification is True


@pytest.mark.asyncio
async def test_candidate_skills_when_medium_confidence(
    router: Router,
    mock_anthropic: MagicMock,
    sample_run: Run,
) -> None:
    mock_anthropic.messages.create.return_value = _make_llm_response(
        {
            "skill_name": "answer_business_question",
            "confidence": 0.65,
            "rationale": "Could be answering a question or discovering a dashboard.",
            "requires_clarification": False,
            "clarification_message": None,
            "candidate_skills": ["answer_business_question", "discover_metrics_and_dashboards"],
        }
    )

    decision = await router.route(sample_run)

    assert "answer_business_question" in decision.candidate_skills
    assert "discover_metrics_and_dashboards" in decision.candidate_skills


def test_prompt_version_id_is_sha256(prompt_loader: PromptLoader) -> None:
    version_id = prompt_loader.get_version_id("classify_request_v1")

    assert isinstance(version_id, str)
    assert len(version_id) == 64
    # Hex characters only
    int(version_id, 16)


@pytest.mark.asyncio
async def test_empty_registry_raises(
    mock_anthropic: MagicMock,
    prompt_loader: PromptLoader,
    sample_run: Run,
) -> None:
    empty_registry = SkillRegistry()
    router = Router(
        registry=empty_registry,
        anthropic_client=mock_anthropic,
        prompt_loader=prompt_loader,
    )

    with pytest.raises(NoSkillsRegisteredError):
        await router.route(sample_run)


@pytest.mark.asyncio
async def test_classification_error_on_invalid_json(
    router: Router,
    mock_anthropic: MagicMock,
    sample_run: Run,
) -> None:
    content_block = MagicMock()
    content_block.text = "this is not valid JSON {{ oops }}"
    bad_response = MagicMock()
    bad_response.content = [content_block]
    mock_anthropic.messages.create.return_value = bad_response

    with pytest.raises(ClassificationError):
        await router.route(sample_run)
