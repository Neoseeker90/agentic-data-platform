from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from contracts.evaluation import EvaluationCase


@dataclass
class ScorerResult:
    metric: str
    value: float
    detail: str = field(default="")


class BaseScorer(ABC):
    @abstractmethod
    def score(
        self,
        case: EvaluationCase,
        actual_skill: str,
        observed_response: str,
    ) -> ScorerResult: ...
