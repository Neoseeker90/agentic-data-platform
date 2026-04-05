from __future__ import annotations

import json
import logging
from pathlib import Path

from contracts.evaluation import EvaluationCase
from evaluation.db.case_store import CaseStore

logger = logging.getLogger(__name__)


class EvalDataset:
    def __init__(self, store: CaseStore) -> None:
        self.store = store

    async def add_case(self, case: EvaluationCase) -> EvaluationCase:
        return await self.store.save(case)

    async def list_cases(
        self,
        tags: list[str] | None = None,
        limit: int = 500,
    ) -> list[EvaluationCase]:
        return await self.store.list_cases(tags=tags, limit=limit)

    async def export_jsonl(self, path: Path, tags: list[str] | None = None) -> int:
        cases = await self.store.list_cases(tags=tags, limit=10_000)
        with path.open("w", encoding="utf-8") as fh:
            for case in cases:
                fh.write(case.model_dump_json() + "\n")
        return len(cases)

    async def import_jsonl(self, path: Path) -> int:
        count = 0
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    case = EvaluationCase.model_validate(data)
                    await self.store.save(case)
                    count += 1
                except Exception:
                    logger.exception("Failed to import line: %r", line)
        return count

    async def size(self) -> int:
        return await self.store.count()
