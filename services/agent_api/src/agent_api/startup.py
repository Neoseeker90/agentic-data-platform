"""AppContainer — builds and holds every singleton dependency.

Created once in the FastAPI lifespan and stored in ``app.state.container``.
"""

from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Any

import anthropic


def _parse_bedrock_token(token: str) -> tuple[str, str]:
    """Parse AWS_BEARER_TOKEN_BEDROCK into (access_key_id, secret_access_key).

    Claude Code encodes the Bedrock credentials as:
      base64( <4-byte binary header> + "{access_key_id}:{secret_access_key}" )

    Returns ("", "") if the token is empty or unparseable — the SDK will then
    fall back to the standard boto3 credential chain (env vars, ~/.aws/credentials).
    """
    if not token:
        return "", ""
    try:
        decoded = base64.b64decode(token).decode("latin-1")
        # Find first printable ASCII segment (skip binary header bytes)
        start = next(
            (i for i, c in enumerate(decoded) if c.isascii() and c.isprintable()),
            0,
        )
        credential_str = decoded[start:]
        if ":" in credential_str:
            key_id, secret = credential_str.split(":", 1)
            return key_id.strip(), secret.strip()
    except Exception:
        pass
    return "", ""


from agent_api.config import Settings  # noqa: E402

# ---------------------------------------------------------------------------
# OpenAI → Anthropic response adapter
# ---------------------------------------------------------------------------
# Skills and the router use client.messages.create() and read response.content[0].text.
# This thin adapter makes an OpenAI AsyncClient expose that same interface so no
# skill or router code needs to change.


class _OpenAIContent:
    def __init__(self, text: str) -> None:
        self.text = text


class _OpenAIAdaptedResponse:
    def __init__(self, oai_response: Any) -> None:
        text = oai_response.choices[0].message.content or ""
        self.content = [_OpenAIContent(text)]
        # Expose usage in Anthropic field names for cost recording
        u = oai_response.usage
        self.usage = type(
            "Usage",
            (),
            {
                "input_tokens": u.prompt_tokens,
                "output_tokens": u.completion_tokens,
            },
        )()


class _OpenAIMessagesAPI:
    def __init__(self, client: Any) -> None:
        self._client = client

    async def create(
        self,
        model: str,
        messages: list[dict],
        max_tokens: int = 1024,
        system: str | None = None,
        **kwargs: Any,
    ) -> _OpenAIAdaptedResponse:
        oai_messages: list[dict] = []
        if system:
            oai_messages.append({"role": "system", "content": system})
        oai_messages.extend(messages)
        response = await self._client.chat.completions.create(
            model=model,
            messages=oai_messages,
            max_tokens=max_tokens,
        )
        return _OpenAIAdaptedResponse(response)


class OpenAIClientAdapter:
    """Wraps openai.AsyncOpenAI to expose the Anthropic messages.create() interface."""

    def __init__(self, openai_client: Any) -> None:
        self.messages = _OpenAIMessagesAPI(openai_client)


from agent_api.db.engine import get_session_factory  # noqa: E402
from agent_api.db.run_store import RunStore  # noqa: E402
from observability.run_auditor import RunAuditor  # noqa: E402
from router.classifier import Router  # noqa: E402
from router.config import RouterConfig  # noqa: E402
from router.prompt import PromptLoader as RouterPromptLoader  # noqa: E402
from skill_sdk.registry import SkillRegistry  # noqa: E402

logger = logging.getLogger(__name__)


class AppContainer:
    """Holds every application-scoped singleton.

    Call ``create(settings)`` once at startup; inject via ``request.app.state.container``.
    """

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._registry: SkillRegistry | None = None
        self._router: Router | None = None
        self._orchestrator = None  # RunOrchestrator — imported lazily to avoid circular deps
        self._indexer = None  # SemanticIndexer — optional, None if vector search disabled

    @classmethod
    def create(cls, settings: Settings) -> AppContainer:
        container = cls(settings)
        container._build()
        return container

    # ------------------------------------------------------------------
    # Public accessors
    # ------------------------------------------------------------------

    @property
    def registry(self) -> SkillRegistry:
        assert self._registry is not None
        return self._registry

    @property
    def router(self) -> Router:
        assert self._router is not None
        return self._router

    @property
    def orchestrator(self):  # type: ignore[return]
        assert self._orchestrator is not None
        return self._orchestrator

    @property
    def indexer(self):
        """SemanticIndexer if vector search is enabled, otherwise None."""
        return self._indexer

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    @staticmethod
    def _build_llm_client(settings: Settings) -> Any:
        """Return the appropriate LLM client for the configured backend.

        Priority: Bedrock > OpenAI > Anthropic direct.
        """
        if settings.use_bedrock:
            logger.info("LLM backend: Amazon Bedrock (region=%s)", settings.aws_region)
            # The SDK reads AWS_BEARER_TOKEN_BEDROCK from the environment automatically
            # and uses it as the api_key for bearer-token Bedrock auth.
            # It's mutually exclusive with aws_access_key / aws_secret_key.
            # Ensure it's set in the environment from our settings if not already there.
            if settings.aws_bearer_token_bedrock:
                os.environ.setdefault("AWS_BEARER_TOKEN_BEDROCK", settings.aws_bearer_token_bedrock)
            return anthropic.AsyncAnthropicBedrock(aws_region=settings.aws_region)
        if settings.openai_api_key:
            try:
                from openai import AsyncOpenAI  # noqa: PLC0415
            except ImportError as exc:
                raise RuntimeError(
                    "OPENAI_API_KEY is set but the 'openai' package is not installed. "
                    "Run: uv add openai"
                ) from exc
            logger.info("LLM backend: OpenAI")
            return OpenAIClientAdapter(AsyncOpenAI(api_key=settings.openai_api_key))
        logger.info("LLM backend: Anthropic API (direct)")
        return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    def _build(self) -> None:
        settings = self.settings
        session_factory = get_session_factory()

        # LLM client — shared across all components
        anthropic_client = self._build_llm_client(settings)

        # Resolved model IDs — Bedrock uses different IDs than the Anthropic API
        planning_model = settings.resolve_model(settings.planning_model)
        execution_model = settings.resolve_model(settings.execution_model)
        router_model = settings.resolve_model(settings.router_model)
        logger.info(
            "Model IDs — router: %s | planning: %s | execution: %s",
            router_model,
            planning_model,
            execution_model,
        )

        # Adapters
        lightdash_search, lightdash_client = self._build_lightdash(settings)
        dbt_reader = self._build_dbt(settings)
        docs_searcher = self._build_docs(settings)

        # Vector search — optional; gracefully disabled if unavailable
        semantic_search, indexer = self._build_vector_search(settings, dbt_reader, lightdash_client)
        self._indexer = indexer

        # Audit + run store
        auditor = RunAuditor(session_factory=session_factory)
        run_store = RunStore(session_factory)

        # Skills — each gets its own PromptLoader pointed at its own prompts dir
        registry = SkillRegistry()
        registry.reset()  # clear any prior state (e.g. in tests)
        registry = SkillRegistry.get_instance()

        self._register_skills(
            registry=registry,
            anthropic_client=anthropic_client,
            lightdash_search=lightdash_search,
            lightdash_client=lightdash_client,
            dbt_reader=dbt_reader,
            docs_searcher=docs_searcher,
            planning_model=planning_model,
            execution_model=execution_model,
            dbt_project_path=settings.dbt_project_path or "",
            semantic_search=semantic_search,
        )
        self._registry = registry

        # Router
        router_prompts_dir = (
            Path(__file__).parent.parent.parent.parent.parent / "packages" / "router" / "prompts"
        )
        router_prompt_loader = RouterPromptLoader(prompts_dir=router_prompts_dir)
        self._router = Router(
            registry=registry,
            anthropic_client=anthropic_client,
            prompt_loader=router_prompt_loader,
            config=RouterConfig(
                confidence_threshold=settings.confidence_threshold,
                clarification_threshold=settings.clarification_threshold,
                model_id=router_model,
            ),
        )

        # Orchestrator
        from skill_sdk.lifecycle import RunOrchestrator  # noqa: PLC0415

        self._orchestrator = RunOrchestrator(
            registry=registry,
            run_store=run_store,
            auditor=auditor,
        )

        logger.info(
            "AppContainer ready — skills: %s",
            [s["name"] for s in registry.list_skills()],
        )

    def _build_lightdash(self, settings: Settings):
        from lightdash_adapter.client import LightdashClient  # noqa: PLC0415
        from lightdash_adapter.search import LightdashSearchService  # noqa: PLC0415

        if not settings.lightdash_url or not settings.lightdash_api_key:
            logger.warning(
                "LIGHTDASH_URL or LIGHTDASH_API_KEY not set — "
                "Lightdash adapter will return empty results"
            )

        client = LightdashClient(
            base_url=settings.lightdash_url or "http://localhost:9999",
            api_key=settings.lightdash_api_key or "dummy",
            project_uuid=getattr(settings, "lightdash_project_uuid", "") or "",
        )
        search = LightdashSearchService(client=client)
        return search, client

    def _build_dbt(self, settings: Settings):
        from dbt_adapter.manifest_reader import DbtManifestReader  # noqa: PLC0415

        if settings.dbt_project_path:
            manifest_path = Path(settings.dbt_project_path) / "target" / "manifest.json"
            if manifest_path.exists():
                reader = DbtManifestReader(manifest_path=manifest_path)
                reader.load()
                logger.info("dbt manifest loaded from %s", manifest_path)
                return reader
            logger.warning("dbt manifest not found at %s — dbt adapter inactive", manifest_path)

        # Return an unloaded reader that will silently return empty results
        return DbtManifestReader(manifest_path=Path("/dev/null"))

    def _build_docs(self, settings: Settings):
        from business_docs_adapter.pg_fts import PgFtsSearcher  # noqa: PLC0415

        return PgFtsSearcher(database_url=settings.database_url)

    def _build_vector_search(self, settings: Settings, dbt_reader: Any, lightdash_client: Any):
        """Build the SemanticSearchService and SemanticIndexer.

        Returns (search_service, indexer) or (None, None) if disabled or vector_store
        package is unavailable.
        """
        if not settings.embedding_enabled:
            logger.info("Semantic search disabled via embedding_enabled=false")
            return None, None
        try:
            from vector_store import BedrockEmbedder, SemanticIndexer, VectorStore  # noqa: PLC0415
            from vector_store.search_service import SemanticSearchService  # noqa: PLC0415
        except ImportError:
            logger.warning("vector_store not available — semantic search disabled")
            return None, None

        store = VectorStore(database_url=settings.database_url)
        embedder = BedrockEmbedder(aws_region=settings.embedding_aws_region)
        search_service = SemanticSearchService(embedder=embedder, store=store)
        indexer = SemanticIndexer(
            embedder=embedder,
            store=store,
            dbt_reader=dbt_reader,
            lightdash_client=lightdash_client,
        )
        logger.info("Vector search configured (region=%s)", settings.embedding_aws_region)
        return search_service, indexer

    def _register_skills(
        self,
        registry: SkillRegistry,
        anthropic_client,
        lightdash_search,
        lightdash_client,
        dbt_reader,
        docs_searcher,
        planning_model: str,
        execution_model: str,
        dbt_project_path: str = "",
        semantic_search=None,
    ) -> None:
        _pkg_root = Path(__file__).parent.parent.parent.parent.parent / "packages"
        # answer_business_question
        from answer_business_question.skill import AnswerBusinessQuestionSkill  # noqa: PLC0415
        from router.prompt import PromptLoader  # noqa: PLC0415

        abq_prompts = _pkg_root / "skills" / "answer_business_question" / "prompts"
        registry.register(
            AnswerBusinessQuestionSkill(
                anthropic_client=anthropic_client,
                prompt_loader=PromptLoader(prompts_dir=abq_prompts),
                lightdash_search=lightdash_search,
                dbt_reader=dbt_reader,
                docs_searcher=docs_searcher,
                planning_model=planning_model,
                execution_model=execution_model,
                semantic_search=semantic_search,
            )
        )

        # discover_metrics_and_dashboards
        from discover_metrics_and_dashboards.skill import (
            DiscoverMetricsAndDashboardsSkill,  # noqa: PLC0415
        )

        dmd_prompts = _pkg_root / "skills" / "discover_metrics_and_dashboards" / "prompts"
        registry.register(
            DiscoverMetricsAndDashboardsSkill(
                anthropic_client=anthropic_client,
                prompt_loader=PromptLoader(prompts_dir=dmd_prompts),
                lightdash_search=lightdash_search,
                lightdash_client=lightdash_client,
                dbt_reader=dbt_reader,
                docs_searcher=docs_searcher,
                planning_model=planning_model,
                execution_model=execution_model,
                semantic_search=semantic_search,
            )
        )

        # explain_metric_definition
        from explain_metric_definition.skill import ExplainMetricDefinitionSkill  # noqa: PLC0415

        emd_prompts = _pkg_root / "skills" / "explain_metric_definition" / "prompts"
        registry.register(
            ExplainMetricDefinitionSkill(
                anthropic_client=anthropic_client,
                prompt_loader=PromptLoader(prompts_dir=emd_prompts),
                lightdash_client=lightdash_client,
                lightdash_search=lightdash_search,
                dbt_reader=dbt_reader,
                docs_searcher=docs_searcher,
                planning_model=planning_model,
                execution_model=execution_model,
                semantic_search=semantic_search,
            )
        )

        # execute_data_question
        from execute_data_question.skill import ExecuteDataQuestionSkill  # noqa: PLC0415

        edq_prompts = _pkg_root / "skills" / "execute_data_question" / "prompts"
        registry.register(
            ExecuteDataQuestionSkill(
                anthropic_client=anthropic_client,
                prompt_loader=PromptLoader(prompts_dir=edq_prompts),
                lightdash_client=lightdash_client,
                planning_model=planning_model,
                execution_model=execution_model,
                dbt_project_path=dbt_project_path,
            )
        )
