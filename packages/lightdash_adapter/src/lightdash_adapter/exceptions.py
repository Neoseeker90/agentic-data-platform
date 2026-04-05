class LightdashError(Exception):
    """Base exception for Lightdash adapter errors."""


class LightdashAuthError(LightdashError):
    """Raised on 401/403 responses from the Lightdash API."""


class LightdashNotFoundError(LightdashError):
    """Raised on 404 responses from the Lightdash API."""


class LightdashConnectionError(LightdashError):
    """Raised on network-level failures when contacting the Lightdash API."""
