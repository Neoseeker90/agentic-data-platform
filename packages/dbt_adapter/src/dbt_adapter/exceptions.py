class DbtAdapterError(Exception):
    """Base exception for dbt adapter errors."""


class ManifestNotFoundError(DbtAdapterError):
    """Raised when the manifest.json file cannot be found at the given path."""


class ManifestParseError(DbtAdapterError):
    """Raised when manifest.json cannot be parsed as valid JSON or has unexpected structure."""
