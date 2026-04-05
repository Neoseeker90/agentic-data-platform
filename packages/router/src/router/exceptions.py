class RouterError(Exception):
    """Base exception for all router errors."""


class ClassificationError(RouterError):
    """Raised when the LLM classification call fails or returns unparseable output."""


class NoSkillsRegisteredError(RouterError):
    """Raised when the skill registry is empty and routing cannot proceed."""
