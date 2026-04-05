#!/usr/bin/env python3
"""CLI runner for the offline evaluation harness.

Usage:
    uv run python scripts/run_eval.py --help
    uv run python scripts/run_eval.py --tags routing --output reports/
    uv run python scripts/run_eval.py --generate-from-feedback --limit 50
    uv run python scripts/run_eval.py --import-cases evals/cases.jsonl
    uv run python scripts/run_eval.py --export-cases evals/export.jsonl
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def main() -> None:
    parser = argparse.ArgumentParser(description="Offline evaluation harness")
    parser.add_argument("--tags", nargs="*", help="Filter cases by tags")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports"),
        help="Output directory",
    )
    parser.add_argument(
        "--generate-from-feedback",
        action="store_true",
        help="Generate eval cases from low-rated runs first",
    )
    parser.add_argument(
        "--score-threshold",
        type=int,
        default=2,
        help="Max score considered low-rated (default 2)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Max cases to generate or evaluate",
    )
    parser.add_argument(
        "--import-cases",
        type=Path,
        help="Import cases from JSONL file",
    )
    parser.add_argument(
        "--export-cases",
        type=Path,
        help="Export dataset to JSONL file",
    )
    parser.add_argument(
        "--no-llm-scorer",
        action="store_true",
        help="Skip AnswerQualityScorer (saves cost)",
    )
    args = parser.parse_args()

    from agent_api.config import Settings
    from agent_api.db.engine import get_session_factory, init_db_engine
    from evaluation.case_generator import EvalCaseGenerator
    from evaluation.dataset import EvalDataset
    from evaluation.db.case_store import CaseStore
    from evaluation.harness import EvalHarness
    from evaluation.report import EvalReportWriter
    from evaluation.scorers.discovery_scorer import DiscoveryRecallScorer
    from evaluation.scorers.routing_scorer import RoutingScorer
    from skill_sdk.registry import SkillRegistry

    settings = Settings()
    init_db_engine(settings.database_url)
    session_factory = get_session_factory()

    store = CaseStore(session_factory)
    dataset = EvalDataset(store)

    # Import mode
    if args.import_cases:
        n = await dataset.import_jsonl(args.import_cases)
        print(f"Imported {n} cases from {args.import_cases}")
        return

    # Export mode
    if args.export_cases:
        args.export_cases.parent.mkdir(parents=True, exist_ok=True)
        n = await dataset.export_jsonl(args.export_cases, tags=args.tags)
        print(f"Exported {n} cases to {args.export_cases}")
        return

    # Generate cases from low-rated feedback
    if args.generate_from_feedback:
        generator = EvalCaseGenerator(session_factory)
        cases = await generator.generate_batch_from_low_rated(
            score_threshold=args.score_threshold,
            limit=args.limit,
        )
        for case in cases:
            await dataset.add_case(case)
        print(f"Generated and saved {len(cases)} eval cases")
        if not cases:
            print(
                "No cases generated — run with feedback first or lower --score-threshold"
            )
            return

    # Run evaluation
    scorers = [RoutingScorer(), DiscoveryRecallScorer()]
    if not args.no_llm_scorer:
        from evaluation.scorers.answer_scorer import AnswerQualityScorer
        import anthropic

        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        scorers.append(AnswerQualityScorer(client))

    registry = SkillRegistry.get_instance()
    harness = EvalHarness(registry=registry, dataset=dataset, scorers=scorers)
    print(f"Running eval on {await dataset.size()} cases (tags={args.tags})...")
    report = await harness.run(tags=args.tags)

    # Write report
    args.output.mkdir(parents=True, exist_ok=True)
    writer = EvalReportWriter()
    md_path = args.output / f"eval_{report.report_id}.md"
    json_path = args.output / f"eval_{report.report_id}.json"
    writer.write_markdown(report, md_path)
    writer.write_json(report, json_path)

    print(
        f"\nResults: {report.passed_cases}/{report.total_cases} passed ({report.pass_rate:.0%})"
    )
    for metric, value in report.metrics.items():
        print(f"  {metric}: {value:.3f}")
    print(f"\nReports written to:\n  {md_path}\n  {json_path}")


if __name__ == "__main__":
    asyncio.run(main())
