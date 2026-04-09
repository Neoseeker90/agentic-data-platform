from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Bedrock cross-region inference profile IDs.
# Keys are Anthropic API model IDs; values are dicts keyed by region prefix.
_BEDROCK_MODEL_MAP: dict[str, dict[str, str]] = {
    "claude-3-haiku-20240307": {
        "us": "us.anthropic.claude-3-haiku-20240307-v1:0",
        "eu": "eu.anthropic.claude-3-haiku-20240307-v1:0",
        "ap": "ap.anthropic.claude-3-haiku-20240307-v1:0",
    },
    "claude-3-5-haiku-20241022": {
        "us": "us.anthropic.claude-3-5-haiku-20241022-v1:0",
        "eu": "eu.anthropic.claude-3-5-haiku-20241022-v1:0",
        "ap": "ap.anthropic.claude-3-5-haiku-20241022-v1:0",
    },
    "claude-3-5-sonnet-20241022": {
        "us": "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
        "eu": "eu.anthropic.claude-3-5-sonnet-20241022-v2:0",
        "ap": "ap.anthropic.claude-3-5-sonnet-20241022-v2:0",
    },
    "claude-3-opus-20240229": {
        "us": "us.anthropic.claude-3-opus-20240229-v1:0",
        "eu": "eu.anthropic.claude-3-opus-20240229-v1:0",
    },
    "claude-sonnet-4-6": {
        "us": "us.anthropic.claude-sonnet-4-5-20251101-v1:0",
        "eu": "eu.anthropic.claude-sonnet-4-5-20251101-v1:0",
    },
    "claude-opus-4-6": {
        "us": "us.anthropic.claude-opus-4-5-20251101-v1:0",
    },
}


def _region_prefix(aws_region: str) -> str:
    """Return the cross-region inference prefix ('us', 'eu', 'ap') for a given region."""
    if aws_region.startswith("eu-"):
        return "eu"
    if aws_region.startswith("ap-"):
        return "ap"
    return "us"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    anthropic_api_key: str = ""
    s3_artifacts_bucket: str = "agent-artifacts"
    aws_endpoint_url: str | None = None
    lightdash_url: str = ""
    lightdash_api_key: str = ""
    lightdash_project_uuid: str = ""
    dbt_project_path: str | None = None
    confidence_threshold: float = 0.75
    clarification_threshold: float = 0.50
    router_model: str = "claude-3-5-haiku-20241022"
    planning_model: str = "claude-3-5-haiku-20241022"
    execution_model: str = "claude-3-5-sonnet-20241022"
    environment: str = "development"
    log_level: str = "INFO"

    # Bedrock — field names map to env vars by uppercasing; use alias for CLAUDE_CODE_USE_BEDROCK
    use_bedrock: bool = Field(default=False, validation_alias="claude_code_use_bedrock")
    aws_region: str = "us-east-1"
    aws_bearer_token_bedrock: str = ""

    # OpenAI (takes effect when set; ignored when use_bedrock=True)
    openai_api_key: str = ""

    # Semantic search / vector embeddings
    embedding_enabled: bool = Field(default=True, validation_alias="embedding_enabled")
    embedding_aws_region: str = "eu-central-1"
    semantic_min_similarity: float = 0.3

    def resolve_model(self, model_id: str) -> str:
        """Return the correct model ID for the configured backend.

        When Bedrock is enabled, maps from Anthropic model IDs to Bedrock
        cross-region inference profile IDs for the configured region.
        If the model_id already looks like a Bedrock ARN (contains ':'),
        it is returned unchanged.
        """
        if not self.use_bedrock or ":" in model_id:
            return model_id
        prefix = _region_prefix(self.aws_region)
        by_prefix = _BEDROCK_MODEL_MAP.get(model_id, {})
        bedrock_id = by_prefix.get(prefix) or by_prefix.get("us")
        if bedrock_id is None:
            # Unknown model — pass through and let Bedrock reject it with a clear error
            return model_id
        return bedrock_id
