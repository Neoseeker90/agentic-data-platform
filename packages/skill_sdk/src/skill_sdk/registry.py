from typing import TYPE_CHECKING

from skill_sdk.exceptions import SkillNotFoundError

if TYPE_CHECKING:
    from skill_sdk.base import Skill


class SkillRegistry:
    """Singleton registry of all available skills.

    Skills are registered at worker startup by importing their modules.
    """

    _instance: "SkillRegistry | None" = None

    def __init__(self) -> None:
        self._skills: dict[str, "Skill"] = {}

    @classmethod
    def get_instance(cls) -> "SkillRegistry":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton — use in tests only."""
        cls._instance = None

    def register(self, skill: "Skill") -> None:
        self._skills[skill.name] = skill

    def get(self, name: str) -> "Skill":
        if name not in self._skills:
            raise SkillNotFoundError(name)
        return self._skills[name]

    def has(self, name: str) -> bool:
        return name in self._skills

    def list_skills(self) -> list[dict[str, str]]:
        return [
            {
                "name": s.name,
                "description": s.description,
                "risk_level": s.risk_level,
                "version": s.version,
            }
            for s in self._skills.values()
        ]

    def all_names(self) -> list[str]:
        return list(self._skills.keys())
