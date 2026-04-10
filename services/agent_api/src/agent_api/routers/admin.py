"""Admin observability router — no auth required, read-only aggregate queries."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query
from sqlalchemy import text

from agent_api.db.engine import get_session_factory

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _safe_float(value) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


def _days_clause(days: int | None, column: str = "r.created_at") -> str:
    if days and days > 0:
        return f"AND {column} >= NOW() - INTERVAL '{days} days'"
    return ""


# ---------------------------------------------------------------------------
# GET /admin/overview
# ---------------------------------------------------------------------------


@router.get("/overview")
async def get_overview(days: int | None = Query(default=None, description="Filter last N days; omit for all time")):
    days_sql = _days_clause(days)
    async with get_session_factory()() as session:
        # --- sessions ---
        sessions_row = (
            await session.execute(
                text(f"""
                    SELECT COUNT(DISTINCT ct.session_id) AS total_sessions
                    FROM conversation_turns ct
                    JOIN runs r ON r.run_id = ct.run_id
                    WHERE 1=1 {days_sql}
                """)
            )
        ).fetchone()
        total_sessions = _safe_int(sessions_row[0]) if sessions_row else 0

        # --- run counts ---
        runs_row = (
            await session.execute(
                text(f"""
                    SELECT
                        COUNT(*) AS total_requests,
                        COUNT(*) FILTER (WHERE state = 'succeeded') AS succeeded,
                        COUNT(*) FILTER (WHERE state = 'failed') AS failed,
                        COUNT(*) FILTER (WHERE state = 'cancelled') AS cancelled
                    FROM runs r
                    WHERE 1=1 {days_sql}
                """)
            )
        ).fetchone()
        total_requests = _safe_int(runs_row[0]) if runs_row else 0
        succeeded = _safe_int(runs_row[1]) if runs_row else 0
        failed = _safe_int(runs_row[2]) if runs_row else 0
        cancelled = _safe_int(runs_row[3]) if runs_row else 0

        # --- bad requests: failed runs OR negative feedback ---
        bad_row = (
            await session.execute(
                text(f"""
                    SELECT COUNT(DISTINCT r.run_id)
                    FROM runs r
                    LEFT JOIN feedback f ON f.run_id = r.run_id
                    WHERE (r.state = 'failed' OR f.helpful = FALSE OR f.score <= 2)
                    {days_sql}
                """)
            )
        ).fetchone()
        bad_requests = _safe_int(bad_row[0]) if bad_row else 0

        # --- cost ---
        cost_row = (
            await session.execute(
                text(f"""
                    SELECT
                        COALESCE(SUM(tcr.estimated_cost_usd), 0) AS total_cost_usd,
                        COALESCE(SUM(tcr.total_tokens), 0) AS total_tokens
                    FROM token_cost_records tcr
                    JOIN runs r ON r.run_id = tcr.run_id
                    WHERE 1=1 {days_sql}
                """)
            )
        ).fetchone()
        total_cost_usd = _safe_float(cost_row[0]) if cost_row else 0.0
        total_tokens = _safe_int(cost_row[1]) if cost_row else 0

        avg_cost_per_request = total_cost_usd / total_requests if total_requests > 0 else 0.0

        # --- latency ---
        latency_row = (
            await session.execute(
                text(f"""
                    SELECT AVG(EXTRACT(EPOCH FROM (r.completed_at - r.created_at)) * 1000)
                    FROM runs r
                    WHERE r.completed_at IS NOT NULL
                    {days_sql}
                """)
            )
        ).fetchone()
        avg_latency_ms = _safe_float(latency_row[0]) if latency_row else 0.0

        # --- feedback ---
        feedback_row = (
            await session.execute(
                text(f"""
                    SELECT
                        COUNT(DISTINCT f.run_id) AS feedback_runs,
                        AVG(f.score) FILTER (WHERE f.score IS NOT NULL) AS avg_score,
                        AVG(CASE WHEN f.helpful = TRUE THEN 1.0 ELSE 0.0 END)
                            FILTER (WHERE f.helpful IS NOT NULL) AS helpful_rate
                    FROM feedback f
                    JOIN runs r ON r.run_id = f.run_id
                    WHERE 1=1 {days_sql}
                """)
            )
        ).fetchone()
        feedback_runs = _safe_int(feedback_row[0]) if feedback_row else 0
        avg_feedback_score = _safe_float(feedback_row[1]) if feedback_row else 0.0
        helpful_rate = _safe_float(feedback_row[2]) if feedback_row else 0.0

        feedback_capture_rate = feedback_runs / total_requests if total_requests > 0 else 0.0
        success_rate = succeeded / total_requests if total_requests > 0 else 0.0

    return {
        "total_sessions": total_sessions,
        "total_requests": total_requests,
        "succeeded": succeeded,
        "failed": failed,
        "cancelled": cancelled,
        "bad_requests": bad_requests,
        "total_cost_usd": round(total_cost_usd, 6),
        "avg_cost_per_request": round(avg_cost_per_request, 6),
        "total_tokens": total_tokens,
        "avg_latency_ms": round(avg_latency_ms, 1),
        "success_rate": round(success_rate, 4),
        "feedback_capture_rate": round(feedback_capture_rate, 4),
        "avg_feedback_score": round(avg_feedback_score, 2),
        "helpful_rate": round(helpful_rate, 4),
    }


# ---------------------------------------------------------------------------
# GET /admin/runs
# ---------------------------------------------------------------------------


@router.get("/runs")
async def list_runs(
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    state: str = Query(default="all"),
    skill: str = Query(default="all"),
    days: int | None = Query(default=None),
    bad_only: bool = Query(default=False),
):
    offset = (page - 1) * limit
    filters = ["1=1"]
    if state != "all":
        filters.append(f"r.state = '{state}'")
    if skill != "all":
        filters.append(f"r.selected_skill = '{skill}'")
    if days and days > 0:
        filters.append(f"r.created_at >= NOW() - INTERVAL '{days} days'")
    if bad_only:
        filters.append("(r.state = 'failed' OR f.helpful = FALSE OR f.score <= 2)")

    where_clause = " AND ".join(filters)

    async with get_session_factory()() as session:
        # total count
        count_row = (
            await session.execute(
                text(f"""
                    SELECT COUNT(DISTINCT r.run_id)
                    FROM runs r
                    LEFT JOIN feedback f ON f.run_id = r.run_id
                    WHERE {where_clause}
                """)
            )
        ).fetchone()
        total = _safe_int(count_row[0]) if count_row else 0

        rows = (
            await session.execute(
                text(f"""
                    SELECT
                        r.run_id,
                        r.user_id,
                        r.interface,
                        r.state,
                        r.selected_skill,
                        r.created_at,
                        r.completed_at,
                        CASE
                            WHEN r.completed_at IS NOT NULL
                            THEN EXTRACT(EPOCH FROM (r.completed_at - r.created_at)) * 1000
                            ELSE NULL
                        END AS total_latency_ms,
                        CASE WHEN f.feedback_id IS NOT NULL THEN TRUE ELSE FALSE END AS has_feedback,
                        f.score AS feedback_score,
                        f.helpful AS feedback_helpful,
                        r.error_message,
                        LEFT(r.request_text, 100) AS request_text,
                        COALESCE(SUM(tcr.estimated_cost_usd), 0) AS total_cost_usd
                    FROM runs r
                    LEFT JOIN LATERAL (
                        SELECT * FROM feedback fb WHERE fb.run_id = r.run_id ORDER BY fb.captured_at DESC LIMIT 1
                    ) f ON TRUE
                    LEFT JOIN token_cost_records tcr ON tcr.run_id = r.run_id
                    WHERE {where_clause}
                    GROUP BY r.run_id, f.feedback_id, f.score, f.helpful
                    ORDER BY r.created_at DESC
                    LIMIT :limit OFFSET :offset
                """),
                {"limit": limit, "offset": offset},
            )
        ).fetchall()

    items = []
    for row in rows:
        items.append({
            "run_id": str(row[0]),
            "user_id": row[1],
            "interface": row[2],
            "state": row[3],
            "selected_skill": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
            "completed_at": row[6].isoformat() if row[6] else None,
            "total_latency_ms": round(_safe_float(row[7]), 1) if row[7] is not None else None,
            "has_feedback": bool(row[8]),
            "feedback_score": _safe_int(row[9]) if row[9] is not None else None,
            "feedback_helpful": row[10],
            "error_message": row[11],
            "request_text": row[12],
            "total_cost_usd": round(_safe_float(row[13]), 6),
        })

    return {
        "total": total,
        "page": page,
        "limit": limit,
        "pages": max(1, (total + limit - 1) // limit),
        "items": items,
    }


# ---------------------------------------------------------------------------
# GET /admin/runs/{run_id}/detail
# ---------------------------------------------------------------------------


@router.get("/runs/{run_id}/detail")
async def get_run_detail(run_id: uuid.UUID):
    async with get_session_factory()() as session:
        # --- run ---
        run_row = (
            await session.execute(
                text("""
                    SELECT run_id, user_id, interface, request_text, state, selected_skill,
                           error_message, created_at, updated_at, routed_at, planned_at,
                           context_built_at, validated_at, executing_at, completed_at
                    FROM runs
                    WHERE run_id = :run_id
                """),
                {"run_id": str(run_id)},
            )
        ).fetchone()
        if run_row is None:
            return {"error": "Run not found"}

        run = {
            "run_id": str(run_row[0]),
            "user_id": run_row[1],
            "interface": run_row[2],
            "request_text": run_row[3],
            "state": run_row[4],
            "selected_skill": run_row[5],
            "error_message": run_row[6],
            "created_at": run_row[7].isoformat() if run_row[7] else None,
            "updated_at": run_row[8].isoformat() if run_row[8] else None,
            "routed_at": run_row[9].isoformat() if run_row[9] else None,
            "planned_at": run_row[10].isoformat() if run_row[10] else None,
            "context_built_at": run_row[11].isoformat() if run_row[11] else None,
            "validated_at": run_row[12].isoformat() if run_row[12] else None,
            "executing_at": run_row[13].isoformat() if run_row[13] else None,
            "completed_at": run_row[14].isoformat() if run_row[14] else None,
        }

        # --- route decision ---
        rd_row = (
            await session.execute(
                text("""
                    SELECT skill_name, confidence, rationale, requires_clarification,
                           clarification_message, model_id, prompt_version_id, decided_at
                    FROM route_decisions
                    WHERE run_id = :run_id
                    ORDER BY decided_at DESC
                    LIMIT 1
                """),
                {"run_id": str(run_id)},
            )
        ).fetchone()
        route_decision = None
        if rd_row:
            route_decision = {
                "skill_name": rd_row[0],
                "confidence": _safe_float(rd_row[1]),
                "rationale": rd_row[2],
                "requires_clarification": rd_row[3],
                "clarification_message": rd_row[4],
                "model_id": rd_row[5],
                "prompt_version_id": rd_row[6],
                "decided_at": rd_row[7].isoformat() if rd_row[7] else None,
            }

        # --- plan ---
        plan_row = (
            await session.execute(
                text("""
                    SELECT intent_summary, extracted_entities, skill_name, model_id, prompt_version_id
                    FROM plans
                    WHERE run_id = :run_id
                    ORDER BY planned_at DESC
                    LIMIT 1
                """),
                {"run_id": str(run_id)},
            )
        ).fetchone()
        plan = None
        if plan_row:
            plan = {
                "intent_summary": plan_row[0],
                "extracted_entities": plan_row[1],
                "skill_name": plan_row[2],
                "model_id": plan_row[3],
                "prompt_version_id": plan_row[4],
            }

        # --- context pack ---
        cp_row = (
            await session.execute(
                text("""
                    SELECT sources, unresolved_ambiguities, token_estimate
                    FROM context_packs
                    WHERE run_id = :run_id
                    ORDER BY built_at DESC
                    LIMIT 1
                """),
                {"run_id": str(run_id)},
            )
        ).fetchone()
        context_pack = None
        if cp_row:
            sources = cp_row[0] or []
            context_pack = {
                "sources_count": len(sources),
                "sources": sources,
                "unresolved_ambiguities": cp_row[1] or [],
                "token_estimate": _safe_int(cp_row[2]),
            }

        # --- validation ---
        val_row = (
            await session.execute(
                text("""
                    SELECT passed, risk_level, checks
                    FROM validation_results
                    WHERE run_id = :run_id
                    ORDER BY validated_at DESC
                    LIMIT 1
                """),
                {"run_id": str(run_id)},
            )
        ).fetchone()
        validation = None
        if val_row:
            validation = {
                "passed": val_row[0],
                "risk_level": val_row[1],
                "checks": val_row[2] or [],
            }

        # --- execution ---
        exec_row = (
            await session.execute(
                text("""
                    SELECT success, output, formatted_response, artifacts, llm_call_ids
                    FROM execution_results
                    WHERE run_id = :run_id
                    ORDER BY executed_at DESC
                    LIMIT 1
                """),
                {"run_id": str(run_id)},
            )
        ).fetchone()
        execution = None
        if exec_row:
            execution = {
                "success": exec_row[0],
                "output": exec_row[1],
                "formatted_response": exec_row[2],
                "artifacts": exec_row[3] or [],
                "llm_call_ids": exec_row[4] or [],
            }

        # --- feedback ---
        fb_row = (
            await session.execute(
                text("""
                    SELECT helpful, score, comment, failure_reason, implicit_signals
                    FROM feedback
                    WHERE run_id = :run_id
                    ORDER BY captured_at DESC
                    LIMIT 1
                """),
                {"run_id": str(run_id)},
            )
        ).fetchone()
        feedback = None
        if fb_row:
            feedback = {
                "helpful": fb_row[0],
                "score": fb_row[1],
                "comment": fb_row[2],
                "failure_reason": fb_row[3],
                "implicit_signals": fb_row[4] or [],
            }

        # --- costs ---
        cost_rows = (
            await session.execute(
                text("""
                    SELECT stage, model_id, prompt_tokens, completion_tokens,
                           estimated_cost_usd, latency_ms
                    FROM token_cost_records
                    WHERE run_id = :run_id
                    ORDER BY recorded_at
                """),
                {"run_id": str(run_id)},
            )
        ).fetchall()
        costs = [
            {
                "stage": r[0],
                "model_id": r[1],
                "prompt_tokens": _safe_int(r[2]),
                "completion_tokens": _safe_int(r[3]),
                "estimated_cost_usd": round(_safe_float(r[4]), 6),
                "latency_ms": _safe_int(r[5]),
            }
            for r in cost_rows
        ]

        # --- session history ---
        # First find the session_id for this run
        session_id_row = (
            await session.execute(
                text("""
                    SELECT session_id FROM conversation_turns
                    WHERE run_id = :run_id
                    LIMIT 1
                """),
                {"run_id": str(run_id)},
            )
        ).fetchone()

        session_history = []
        if session_id_row:
            hist_rows = (
                await session.execute(
                    text("""
                        SELECT role, content, created_at
                        FROM conversation_turns
                        WHERE session_id = :session_id
                        ORDER BY created_at DESC
                        LIMIT 10
                    """),
                    {"session_id": str(session_id_row[0])},
                )
            ).fetchall()
            session_history = [
                {
                    "role": r[0],
                    "content": r[1],
                    "created_at": r[2].isoformat() if r[2] else None,
                }
                for r in reversed(hist_rows)
            ]

    return {
        "run": run,
        "route_decision": route_decision,
        "plan": plan,
        "context_pack": context_pack,
        "validation": validation,
        "execution": execution,
        "feedback": feedback,
        "costs": costs,
        "session_history": session_history,
    }


# ---------------------------------------------------------------------------
# GET /admin/skills
# ---------------------------------------------------------------------------


@router.get("/skills")
async def get_skills_breakdown(days: int | None = Query(default=None)):
    days_sql = _days_clause(days)
    async with get_session_factory()() as session:
        rows = (
            await session.execute(
                text(f"""
                    SELECT
                        r.selected_skill,
                        COUNT(*) AS total_runs,
                        COUNT(*) FILTER (WHERE r.state = 'succeeded') AS succeeded,
                        COUNT(*) FILTER (WHERE r.state = 'failed') AS failed,
                        AVG(EXTRACT(EPOCH FROM (r.completed_at - r.created_at)) * 1000)
                            FILTER (WHERE r.completed_at IS NOT NULL) AS avg_latency_ms,
                        COALESCE(AVG(tcr.avg_cost), 0) AS avg_cost_usd,
                        AVG(f.score) FILTER (WHERE f.score IS NOT NULL) AS avg_feedback_score,
                        AVG(CASE WHEN f.helpful = TRUE THEN 1.0 ELSE 0.0 END)
                            FILTER (WHERE f.helpful IS NOT NULL) AS helpful_rate,
                        AVG(CASE WHEN rd.requires_clarification = TRUE THEN 1.0 ELSE 0.0 END)
                            FILTER (WHERE rd.requires_clarification IS NOT NULL) AS clarification_rate
                    FROM runs r
                    LEFT JOIN LATERAL (
                        SELECT AVG(estimated_cost_usd) AS avg_cost
                        FROM token_cost_records t WHERE t.run_id = r.run_id
                    ) tcr ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT score, helpful FROM feedback fb
                        WHERE fb.run_id = r.run_id ORDER BY fb.captured_at DESC LIMIT 1
                    ) f ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT requires_clarification FROM route_decisions rrd
                        WHERE rrd.run_id = r.run_id ORDER BY rrd.decided_at DESC LIMIT 1
                    ) rd ON TRUE
                    WHERE r.selected_skill IS NOT NULL {days_sql}
                    GROUP BY r.selected_skill
                    ORDER BY total_runs DESC
                """)
            )
        ).fetchall()

    result = []
    for row in rows:
        total = _safe_int(row[1])
        succeeded = _safe_int(row[2])
        result.append({
            "skill_name": row[0],
            "total_runs": total,
            "succeeded": succeeded,
            "failed": _safe_int(row[3]),
            "success_rate": round(succeeded / total, 4) if total > 0 else 0.0,
            "avg_latency_ms": round(_safe_float(row[4]), 1),
            "avg_cost_usd": round(_safe_float(row[5]), 6),
            "avg_feedback_score": round(_safe_float(row[6]), 2),
            "helpful_rate": round(_safe_float(row[7]), 4),
            "clarification_rate": round(_safe_float(row[8]), 4),
        })

    return {"skills": result}


# ---------------------------------------------------------------------------
# GET /admin/costs
# ---------------------------------------------------------------------------


@router.get("/costs")
async def get_costs(days: int = Query(default=7, ge=1)):
    days_sql = f"AND r.created_at >= NOW() - INTERVAL '{days} days'"

    async with get_session_factory()() as session:
        # summary
        summary_row = (
            await session.execute(
                text(f"""
                    SELECT
                        COALESCE(SUM(tcr.estimated_cost_usd), 0) AS total_cost_usd,
                        COALESCE(SUM(tcr.total_tokens), 0) AS total_tokens,
                        COUNT(*) AS total_calls,
                        AVG(tcr.estimated_cost_usd) AS avg_cost_per_call
                    FROM token_cost_records tcr
                    JOIN runs r ON r.run_id = tcr.run_id
                    WHERE 1=1 {days_sql}
                """)
            )
        ).fetchone()

        summary = {
            "total_cost_usd": round(_safe_float(summary_row[0]), 6),
            "total_tokens": _safe_int(summary_row[1]),
            "total_calls": _safe_int(summary_row[2]),
            "avg_cost_per_call": round(_safe_float(summary_row[3]), 6),
        }

        # by stage
        stage_rows = (
            await session.execute(
                text(f"""
                    SELECT
                        tcr.stage,
                        SUM(tcr.estimated_cost_usd) AS total_cost_usd,
                        SUM(tcr.total_tokens) AS total_tokens,
                        AVG(tcr.latency_ms) AS avg_latency_ms,
                        COUNT(*) AS call_count
                    FROM token_cost_records tcr
                    JOIN runs r ON r.run_id = tcr.run_id
                    WHERE 1=1 {days_sql}
                    GROUP BY tcr.stage
                    ORDER BY total_cost_usd DESC
                """)
            )
        ).fetchall()

        by_stage = [
            {
                "stage": r[0],
                "total_cost_usd": round(_safe_float(r[1]), 6),
                "total_tokens": _safe_int(r[2]),
                "avg_latency_ms": round(_safe_float(r[3]), 1),
                "call_count": _safe_int(r[4]),
            }
            for r in stage_rows
        ]

        # by model
        model_rows = (
            await session.execute(
                text(f"""
                    SELECT
                        tcr.model_id,
                        SUM(tcr.estimated_cost_usd) AS total_cost_usd,
                        SUM(tcr.total_tokens) AS total_tokens,
                        COUNT(*) AS call_count
                    FROM token_cost_records tcr
                    JOIN runs r ON r.run_id = tcr.run_id
                    WHERE 1=1 {days_sql}
                    GROUP BY tcr.model_id
                    ORDER BY total_cost_usd DESC
                """)
            )
        ).fetchall()

        by_model = [
            {
                "model_id": r[0],
                "total_cost_usd": round(_safe_float(r[1]), 6),
                "total_tokens": _safe_int(r[2]),
                "call_count": _safe_int(r[3]),
            }
            for r in model_rows
        ]

        # by skill
        skill_rows = (
            await session.execute(
                text(f"""
                    SELECT
                        tcr.skill_name,
                        SUM(tcr.estimated_cost_usd) AS total_cost_usd,
                        SUM(tcr.total_tokens) AS total_tokens
                    FROM token_cost_records tcr
                    JOIN runs r ON r.run_id = tcr.run_id
                    WHERE tcr.skill_name IS NOT NULL {days_sql}
                    GROUP BY tcr.skill_name
                    ORDER BY total_cost_usd DESC
                """)
            )
        ).fetchall()

        by_skill = [
            {
                "skill_name": r[0],
                "total_cost_usd": round(_safe_float(r[1]), 6),
                "total_tokens": _safe_int(r[2]),
            }
            for r in skill_rows
        ]

        # daily breakdown
        daily_rows = (
            await session.execute(
                text(f"""
                    SELECT
                        DATE(r.created_at) AS day,
                        SUM(tcr.estimated_cost_usd) AS total_cost_usd,
                        SUM(tcr.total_tokens) AS total_tokens,
                        COUNT(*) AS call_count
                    FROM token_cost_records tcr
                    JOIN runs r ON r.run_id = tcr.run_id
                    WHERE 1=1 {days_sql}
                    GROUP BY DATE(r.created_at)
                    ORDER BY day ASC
                """)
            )
        ).fetchall()

        daily = [
            {
                "date": str(r[0]),
                "total_cost_usd": round(_safe_float(r[1]), 6),
                "total_tokens": _safe_int(r[2]),
                "call_count": _safe_int(r[3]),
            }
            for r in daily_rows
        ]

    return {
        "summary": summary,
        "by_stage": by_stage,
        "by_model": by_model,
        "by_skill": by_skill,
        "daily": daily,
    }


# ---------------------------------------------------------------------------
# GET /admin/feedback
# ---------------------------------------------------------------------------


@router.get("/feedback")
async def get_feedback(days: int | None = Query(default=None)):
    days_sql = _days_clause(days, column="f.captured_at")

    async with get_session_factory()() as session:
        # total requests for capture rate
        req_count_row = (
            await session.execute(text("SELECT COUNT(*) FROM runs"))
        ).fetchone()
        total_requests = _safe_int(req_count_row[0]) if req_count_row else 0

        # summary
        summary_row = (
            await session.execute(
                text(f"""
                    SELECT
                        COUNT(*) AS total_feedback,
                        AVG(score) FILTER (WHERE score IS NOT NULL) AS avg_score,
                        AVG(CASE WHEN helpful = TRUE THEN 1.0 ELSE 0.0 END)
                            FILTER (WHERE helpful IS NOT NULL) AS helpful_rate,
                        COUNT(DISTINCT run_id) AS feedback_runs
                    FROM feedback f
                    WHERE 1=1 {days_sql}
                """)
            )
        ).fetchone()

        total_feedback = _safe_int(summary_row[0]) if summary_row else 0
        avg_score = _safe_float(summary_row[1]) if summary_row else 0.0
        helpful_rate = _safe_float(summary_row[2]) if summary_row else 0.0
        feedback_runs = _safe_int(summary_row[3]) if summary_row else 0
        feedback_capture_rate = feedback_runs / total_requests if total_requests > 0 else 0.0

        # failure reasons
        reason_rows = (
            await session.execute(
                text(f"""
                    SELECT
                        failure_reason,
                        COUNT(*) AS cnt
                    FROM feedback f
                    WHERE failure_reason IS NOT NULL {days_sql}
                    GROUP BY failure_reason
                    ORDER BY cnt DESC
                """)
            )
        ).fetchall()
        total_reasons = sum(_safe_int(r[1]) for r in reason_rows)
        failure_reasons = [
            {
                "reason": r[0],
                "count": _safe_int(r[1]),
                "pct": round(_safe_int(r[1]) / total_reasons * 100, 1) if total_reasons > 0 else 0.0,
            }
            for r in reason_rows
        ]

        # implicit signals — unnest JSONB array
        signal_rows = (
            await session.execute(
                text(f"""
                    SELECT sig, COUNT(*) AS cnt
                    FROM feedback f,
                         LATERAL jsonb_array_elements_text(
                             CASE WHEN jsonb_typeof(implicit_signals::jsonb) = 'array'
                             THEN implicit_signals::jsonb
                             ELSE '[]'::jsonb END
                         ) AS sig
                    WHERE 1=1 {days_sql}
                    GROUP BY sig
                    ORDER BY cnt DESC
                """)
            )
        ).fetchall()
        implicit_signals = [
            {"signal": r[0], "count": _safe_int(r[1])}
            for r in signal_rows
        ]

        # score distribution
        score_rows = (
            await session.execute(
                text(f"""
                    SELECT score, COUNT(*) AS cnt
                    FROM feedback f
                    WHERE score IS NOT NULL {days_sql}
                    GROUP BY score
                    ORDER BY score
                """)
            )
        ).fetchall()
        score_distribution = [{"score": _safe_int(r[0]), "count": _safe_int(r[1])} for r in score_rows]

        # low rated runs
        low_rows = (
            await session.execute(
                text(f"""
                    SELECT DISTINCT run_id
                    FROM feedback f
                    WHERE (score <= 2 OR helpful = FALSE) {days_sql}
                    LIMIT 20
                """)
            )
        ).fetchall()
        low_rated_runs = [str(r[0]) for r in low_rows]

    return {
        "summary": {
            "total_feedback": total_feedback,
            "avg_score": round(avg_score, 2),
            "helpful_rate": round(helpful_rate, 4),
            "feedback_capture_rate": round(feedback_capture_rate, 4),
        },
        "failure_reasons": failure_reasons,
        "implicit_signals": implicit_signals,
        "score_distribution": score_distribution,
        "low_rated_runs": low_rated_runs,
    }


# ---------------------------------------------------------------------------
# GET /admin/routing
# ---------------------------------------------------------------------------


@router.get("/routing")
async def get_routing(days: int | None = Query(default=None)):
    days_sql = _days_clause(days, column="rd.decided_at")

    async with get_session_factory()() as session:
        # summary stats
        stats_row = (
            await session.execute(
                text(f"""
                    SELECT
                        AVG(rd.confidence) AS avg_confidence,
                        AVG(CASE WHEN rd.confidence < 0.7 THEN 1.0 ELSE 0.0 END) AS low_confidence_rate,
                        AVG(CASE WHEN rd.requires_clarification = TRUE THEN 1.0 ELSE 0.0 END) AS clarification_rate,
                        COUNT(*) AS total_decisions
                    FROM route_decisions rd
                    WHERE 1=1 {days_sql}
                """)
            )
        ).fetchone()

        avg_confidence = _safe_float(stats_row[0]) if stats_row else 0.0
        low_confidence_rate = _safe_float(stats_row[1]) if stats_row else 0.0
        clarification_rate = _safe_float(stats_row[2]) if stats_row else 0.0
        total_decisions = _safe_int(stats_row[3]) if stats_row else 0

        # skill distribution
        skill_rows = (
            await session.execute(
                text(f"""
                    SELECT rd.skill_name, COUNT(*) AS cnt
                    FROM route_decisions rd
                    WHERE 1=1 {days_sql}
                    GROUP BY rd.skill_name
                    ORDER BY cnt DESC
                """)
            )
        ).fetchall()
        skill_distribution = [
            {
                "skill_name": r[0],
                "count": _safe_int(r[1]),
                "pct": round(_safe_int(r[1]) / total_decisions * 100, 1) if total_decisions > 0 else 0.0,
            }
            for r in skill_rows
        ]

        # confidence distribution
        bucket_rows = (
            await session.execute(
                text(f"""
                    SELECT
                        CASE
                            WHEN confidence < 0.5 THEN '0.0-0.5'
                            WHEN confidence < 0.7 THEN '0.5-0.7'
                            WHEN confidence < 0.9 THEN '0.7-0.9'
                            ELSE '0.9-1.0'
                        END AS bucket,
                        COUNT(*) AS cnt
                    FROM route_decisions rd
                    WHERE 1=1 {days_sql}
                    GROUP BY bucket
                    ORDER BY bucket
                """)
            )
        ).fetchall()
        confidence_distribution = [
            {"bucket": r[0], "count": _safe_int(r[1])}
            for r in bucket_rows
        ]

    return {
        "avg_confidence": round(avg_confidence, 4),
        "low_confidence_rate": round(low_confidence_rate, 4),
        "clarification_rate": round(clarification_rate, 4),
        "total_decisions": total_decisions,
        "skill_distribution": skill_distribution,
        "confidence_distribution": confidence_distribution,
    }


# ---------------------------------------------------------------------------
# GET /admin/evals
# ---------------------------------------------------------------------------


@router.get("/evals")
async def get_evals(days: int | None = Query(default=None)):
    days_sql = _days_clause(days, column="ec.created_at")

    async with get_session_factory()() as session:
        # summary
        summary_row = (
            await session.execute(
                text(f"""
                    SELECT
                        COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE status = 'failing') AS failing,
                        COUNT(*) FILTER (WHERE status = 'passing') AS passing,
                        COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                        COUNT(*) FILTER (WHERE created_by = 'auto') AS auto_created,
                        COUNT(*) FILTER (WHERE created_by != 'auto') AS human_created
                    FROM evaluation_cases ec
                    WHERE 1=1 {days_sql}
                """)
            )
        ).fetchone()

        total = _safe_int(summary_row[0]) if summary_row else 0
        failing = _safe_int(summary_row[1]) if summary_row else 0
        passing = _safe_int(summary_row[2]) if summary_row else 0
        pending = _safe_int(summary_row[3]) if summary_row else 0
        auto_created = _safe_int(summary_row[4]) if summary_row else 0
        human_created = _safe_int(summary_row[5]) if summary_row else 0

        # by failure reason
        reason_rows = (
            await session.execute(
                text(f"""
                    SELECT feedback_failure_reason, COUNT(*) AS cnt
                    FROM evaluation_cases ec
                    WHERE feedback_failure_reason IS NOT NULL {days_sql}
                    GROUP BY feedback_failure_reason
                    ORDER BY cnt DESC
                """)
            )
        ).fetchall()
        by_failure_reason = [
            {"reason": r[0], "count": _safe_int(r[1])}
            for r in reason_rows
        ]

        # recent failing cases
        failing_rows = (
            await session.execute(
                text(f"""
                    SELECT
                        ec.case_id,
                        LEFT(ec.request_text, 120) AS request_text,
                        ec.expected_skill,
                        ec.observed_skill,
                        ec.created_at
                    FROM evaluation_cases ec
                    WHERE ec.status = 'failing' {days_sql}
                    ORDER BY ec.created_at DESC
                    LIMIT 20
                """)
            )
        ).fetchall()
        recent_failing = [
            {
                "case_id": str(r[0]),
                "request_text": r[1],
                "expected_skill": r[2],
                "observed_skill": r[3],
                "created_at": r[4].isoformat() if r[4] else None,
            }
            for r in failing_rows
        ]

    return {
        "total": total,
        "failing": failing,
        "passing": passing,
        "pending": pending,
        "auto_created": auto_created,
        "human_created": human_created,
        "by_failure_reason": by_failure_reason,
        "recent_failing": recent_failing,
    }
