"""
Seed business documentation into the business_docs table.
Usage: uv run python scripts/seed_docs.py --docs-dir path/to/docs/
"""
import argparse
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main(docs_dir: Path) -> None:
    from business_docs_adapter.indexer import BusinessDocsIndexer  # noqa: PLC0415

    database_url = os.environ["DATABASE_URL"]
    indexer = BusinessDocsIndexer(database_url=database_url)
    await indexer.index_directory(docs_dir)
    print(f"Seeded documents from {docs_dir}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--docs-dir", type=Path, required=True)
    args = parser.parse_args()
    asyncio.run(main(args.docs_dir))
