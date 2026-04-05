"""Tests for SkillRegistry."""

from unittest.mock import MagicMock

import pytest

from skill_sdk.exceptions import SkillNotFoundError
from skill_sdk.registry import SkillRegistry


@pytest.fixture(autouse=True)
def reset_registry() -> None:  # type: ignore
    SkillRegistry.reset()
    yield
    SkillRegistry.reset()


def make_skill(name: str) -> MagicMock:
    skill = MagicMock()
    skill.name = name
    skill.description = f"Description for {name}"
    skill.risk_level = "read_only"
    skill.version = "1.0.0"
    return skill


class TestSkillRegistry:
    def test_singleton(self) -> None:
        r1 = SkillRegistry.get_instance()
        r2 = SkillRegistry.get_instance()
        assert r1 is r2

    def test_register_and_get(self) -> None:
        registry = SkillRegistry.get_instance()
        skill = make_skill("answer_business_question")
        registry.register(skill)
        assert registry.get("answer_business_question") is skill

    def test_not_found_raises(self) -> None:
        registry = SkillRegistry.get_instance()
        with pytest.raises(SkillNotFoundError) as exc_info:
            registry.get("nonexistent_skill")
        assert "nonexistent_skill" in str(exc_info.value)

    def test_has(self) -> None:
        registry = SkillRegistry.get_instance()
        skill = make_skill("test_skill")
        assert not registry.has("test_skill")
        registry.register(skill)
        assert registry.has("test_skill")

    def test_list_skills(self) -> None:
        registry = SkillRegistry.get_instance()
        registry.register(make_skill("skill_a"))
        registry.register(make_skill("skill_b"))
        names = [s["name"] for s in registry.list_skills()]
        assert "skill_a" in names
        assert "skill_b" in names

    def test_all_names(self) -> None:
        registry = SkillRegistry.get_instance()
        registry.register(make_skill("x"))
        assert "x" in registry.all_names()
