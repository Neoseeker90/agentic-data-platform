"""Structured logging configuration using structlog."""

from __future__ import annotations

import contextvars
import logging
import sys
from typing import Any

import structlog

run_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "run_id", default=None
)
skill_name_var: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "skill_name", default=None
)


def _add_run_context(
    logger: Any,  # noqa: ANN001
    method: str,
    event_dict: dict[str, Any],
) -> dict[str, Any]:
    """Structlog processor that injects run_id/skill_name from contextvars."""
    run_id = run_id_var.get()
    if run_id is not None:
        event_dict["run_id"] = run_id

    skill_name = skill_name_var.get()
    if skill_name is not None:
        event_dict["skill_name"] = skill_name

    return event_dict


def configure_logging(level: str = "INFO", json_logs: bool = False) -> None:
    """Configure structlog.  Call once at application startup.

    In production (``json_logs=True``) log lines are emitted as JSON objects.
    In development the human-friendly :class:`structlog.dev.ConsoleRenderer`
    is used instead.

    ``run_id`` and ``skill_name`` are automatically added to every log entry
    when they have been set via :func:`bind_run_context`.
    """
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        _add_run_context,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if json_logs:
        renderer: Any = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=shared_processors,
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structlog :class:`~structlog.stdlib.BoundLogger` for *name*."""
    return structlog.get_logger(name)


def bind_run_context(run_id: str, skill_name: str | None = None) -> None:
    """Bind run context into contextvars for all subsequent log calls in this task."""
    run_id_var.set(run_id)
    if skill_name is not None:
        skill_name_var.set(skill_name)
