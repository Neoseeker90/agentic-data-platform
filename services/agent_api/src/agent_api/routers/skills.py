from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()

# Human-friendly metadata for each skill.
# Keys are the internal skill names registered in the SkillRegistry.
_SKILL_META: dict[str, dict[str, str | list[str]]] = {
    "execute_data_question": {
        "label": "Build charts & query data",
        "description": "Get actual numbers, trends, and charts from your data",
        "examples": [
            "net sales by BU last month",
            "show CM3 per month as a bar chart",
            "top 10 products by revenue in 2025",
        ],
    },
    "answer_business_question": {
        "label": "Answer business questions",
        "description": "Get qualitative, context-driven answers using your metrics and dashboards",
        "examples": [
            "why did revenue drop in Q3?",
            "what factors drive our CM3?",
            "what should we focus on to improve margins?",
        ],
    },
    "explain_metric_definition": {
        "label": "Explain a metric",
        "description": "Understand what a metric means, how it's calculated, and its caveats",
        "examples": [
            "what does CM3 mean?",
            "how is net sales calculated?",
            "explain contribution margin",
        ],
    },
    "discover_metrics_and_dashboards": {
        "label": "Find dashboards & metrics",
        "description": "Discover what dashboards, charts, and metrics are available",
        "examples": [
            "what dashboards do we have for revenue?",
            "do we have a metric for CM3?",
            "show me available analytics for Amazon",
        ],
    },
}


@router.get("/skills")
async def list_skills(request: Request) -> dict:
    """Return all registered skills with human-friendly descriptions."""
    registry = request.app.state.container.registry
    registered_names = registry.all_names()

    skills = []
    for name in registered_names:
        meta = _SKILL_META.get(name, {})
        skills.append(
            {
                "name": name,
                "label": meta.get("label", name),
                "description": meta.get("description", ""),
                "examples": meta.get("examples", []),
            }
        )

    return {"skills": skills}
