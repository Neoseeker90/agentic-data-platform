from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os

import httpx

from .exceptions import EmbeddingError

logger = logging.getLogger(__name__)

_TITAN_MODEL_ID = "amazon.titan-embed-text-v2:0"
_DIMENSIONS = 1024


class BedrockEmbedder:
    """Calls AWS Bedrock Titan Embed v2 via direct HTTP with bearer-token auth.

    AWS_BEARER_TOKEN_BEDROCK is a proprietary bearer token used by both the
    Anthropic SDK and this embedder.  It is sent as ``Authorization: Bearer
    {token}`` — the same mechanism the Anthropic SDK uses internally for
    Bedrock, which avoids the need for SigV4 signing.
    """

    def __init__(self, aws_region: str = "eu-central-1") -> None:
        self._aws_region = aws_region
        self._base_url = f"https://bedrock-runtime.{aws_region}.amazonaws.com"
        self._http: httpx.AsyncClient | None = None

    def _client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            token = os.environ.get("AWS_BEARER_TOKEN_BEDROCK", "")
            self._http = httpx.AsyncClient(
                base_url=self._base_url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                timeout=30.0,
            )
        return self._http

    async def embed_text(self, text: str) -> list[float]:
        """Return a 1024-dim normalised embedding for the given text."""
        try:
            body = json.dumps(
                {"inputText": text[:8000], "dimensions": _DIMENSIONS, "normalize": True}
            )
            r = await self._client().post(f"/model/{_TITAN_MODEL_ID}/invoke", content=body)
            r.raise_for_status()
            return r.json()["embedding"]
        except Exception as exc:
            raise EmbeddingError(f"Bedrock embed failed: {exc}") from exc

    async def embed_batch(self, texts: list[str], batch_size: int = 10) -> list[list[float]]:
        """Embed multiple texts concurrently in chunks."""
        results: list[list[float]] = []
        for i in range(0, len(texts), batch_size):
            chunk = texts[i : i + batch_size]
            embeddings = await asyncio.gather(*(self.embed_text(t) for t in chunk))
            results.extend(embeddings)
        return results

    async def close(self) -> None:
        if self._http is not None and not self._http.is_closed:
            await self._http.aclose()

    @staticmethod
    def content_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
