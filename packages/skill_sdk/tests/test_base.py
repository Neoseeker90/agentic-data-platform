"""Tests for Skill ABC."""

import pytest

from skill_sdk.base import Skill
from skill_sdk.exceptions import (
    ApprovalRequiredError,
    ContextBuildError,
    ExecutionError,
    PlanningError,
    SkillNotFoundError,
    ValidationFailedError,
)


def test_skill_is_abstract() -> None:
    with pytest.raises(TypeError):
        Skill()  # type: ignore[abstract]


def test_exceptions_instantiate() -> None:
    assert SkillNotFoundError("foo").skill_name == "foo"
    assert "foo" in str(SkillNotFoundError("foo"))

    err = ValidationFailedError("bad", errors=["e1", "e2"])
    assert err.errors == ["e1", "e2"]

    ap = ApprovalRequiredError("run-1", "plan-1")
    assert "run-1" in str(ap)

    assert PlanningError("oops")
    assert ContextBuildError("oops")
    assert ExecutionError("oops")
