from pydantic import BaseModel, Field


class RouterConfig(BaseModel):
    """Configuration for the Router classifier."""

    confidence_threshold: float = Field(
        default=0.75,
        ge=0.0,
        le=1.0,
        description="Confidence level at or above which the request is routed immediately.",
    )
    clarification_threshold: float = Field(
        default=0.50,
        ge=0.0,
        le=1.0,
        description="Confidence level below which clarification is always requested.",
    )
    model_id: str = "claude-3-haiku-20240307"
    max_tokens: int = 512
    prompt_name: str = "classify_request_v1"
