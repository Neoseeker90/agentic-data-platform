from __future__ import annotations

from pathlib import Path

import asyncpg

from .models import BusinessDoc, DocType


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse optional YAML frontmatter delimited by '---' lines.

    Returns a tuple of (frontmatter_dict, body_text).
    """
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text

    frontmatter_lines: list[str] = []
    body_start = len(lines)
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            body_start = idx + 1
            break
        frontmatter_lines.append(line)

    metadata: dict[str, str] = {}
    for line in frontmatter_lines:
        if ":" in line:
            key, _, value = line.partition(":")
            metadata[key.strip()] = value.strip()

    body = "".join(lines[body_start:])
    return metadata, body


class BusinessDocsIndexer:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url

    async def index_document(self, doc: BusinessDoc) -> None:
        """Insert or update a document in the business_docs table.

        The search_vector column is a GENERATED ALWAYS column and must not
        be included in the INSERT/UPDATE statement.
        """
        conn = await asyncpg.connect(self._database_url)
        try:
            await conn.execute(
                """
                INSERT INTO business_docs (
                    doc_id, doc_type, title, content, owner, source_path, updated_at
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (doc_id) DO UPDATE
                    SET doc_type   = EXCLUDED.doc_type,
                        title      = EXCLUDED.title,
                        content    = EXCLUDED.content,
                        owner      = EXCLUDED.owner,
                        source_path = EXCLUDED.source_path,
                        updated_at = EXCLUDED.updated_at
                """,
                doc.doc_id,
                str(doc.doc_type),
                doc.title,
                doc.content,
                doc.owner,
                doc.source_path,
                doc.updated_at,
            )
        finally:
            await conn.close()

    async def index_directory(self, directory: Path) -> int:
        """Walk a directory for .md and .txt files and index each one.

        Parses optional YAML frontmatter for doc_type and owner.
        Defaults doc_type to "business_logic" if not present in frontmatter.

        Returns the number of documents successfully indexed.
        """
        count = 0
        for file_path in sorted(directory.rglob("*")):
            if file_path.suffix not in (".md", ".txt"):
                continue
            if not file_path.is_file():
                continue

            text = file_path.read_text(encoding="utf-8")
            metadata, body = _parse_frontmatter(text)

            raw_doc_type = metadata.get("doc_type", "business_logic")
            try:
                doc_type = DocType(raw_doc_type)
            except ValueError:
                doc_type = DocType.BUSINESS_LOGIC

            owner = metadata.get("owner")
            title = file_path.stem.replace("_", " ").replace("-", " ").title()

            doc = BusinessDoc(
                doc_type=doc_type,
                title=title,
                content=body.strip(),
                owner=owner,
                source_path=str(file_path),
            )

            await self.index_document(doc)
            count += 1

        return count
