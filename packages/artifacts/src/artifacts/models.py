"""Artifact domain models."""

from __future__ import annotations

from enum import StrEnum

from contracts.artifact import Artifact  # re-exported for convenience

__all__ = ["Artifact", "ArtifactType"]


class ArtifactType(StrEnum):
    RUN_BUNDLE = "run_bundle"
    CONTEXT_PACK = "context_pack"
    RESPONSE = "response"
    REPORT = "report"
