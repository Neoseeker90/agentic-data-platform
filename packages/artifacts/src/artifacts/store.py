"""ArtifactStore — async S3-backed artifact storage."""

from __future__ import annotations

import json

import aioboto3


class ArtifactStore:
    """Stores and retrieves JSON artifacts in S3 (or any S3-compatible endpoint).

    Parameters
    ----------
    bucket:
        Name of the S3 bucket.
    endpoint_url:
        Optional custom endpoint URL (e.g. for MinIO or LocalStack).
    region:
        AWS region name.  Defaults to ``"us-east-1"``.
    """

    def __init__(
        self,
        bucket: str,
        endpoint_url: str | None = None,
        region: str = "us-east-1",
    ) -> None:
        self._bucket = bucket
        self._endpoint_url = endpoint_url
        self._region = region
        self._session = aioboto3.Session()

    def _make_key(
        self,
        run_id: str,
        artifact_type: str,
        suffix: str = "json",
    ) -> str:
        """Return a canonical S3 object key for the artifact."""
        return f"runs/{run_id}/{artifact_type}.{suffix}"

    async def store_json(
        self,
        run_id: str,
        artifact_type: str,
        data: dict,
    ) -> str:
        """Serialize *data* to JSON and upload it to S3.

        Returns the S3 object key under which the artifact was stored.
        """
        key = self._make_key(run_id, artifact_type)
        body = json.dumps(data, default=str).encode()

        async with self._session.client(
            "s3",
            region_name=self._region,
            endpoint_url=self._endpoint_url,
        ) as s3:
            await s3.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
            )

        return key

    async def get_json(self, key: str) -> dict:
        """Download the object at *key* from S3 and deserialize it as JSON."""
        async with self._session.client(
            "s3",
            region_name=self._region,
            endpoint_url=self._endpoint_url,
        ) as s3:
            response = await s3.get_object(Bucket=self._bucket, Key=key)
            body = await response["Body"].read()

        return json.loads(body)

    async def store_run_bundle(self, run_id: str, bundle: dict) -> str:
        """Convenience wrapper: store a run bundle artifact."""
        return await self.store_json(run_id, "run_bundle", bundle)

    async def get_run_bundle(self, run_id: str) -> dict:
        """Convenience wrapper: retrieve a run bundle artifact."""
        key = self._make_key(run_id, "run_bundle")
        return await self.get_json(key)
