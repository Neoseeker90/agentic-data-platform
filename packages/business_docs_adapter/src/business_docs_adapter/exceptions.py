class BusinessDocsError(Exception):
    """Base exception for business docs adapter errors."""


class IndexError(BusinessDocsError):
    """Raised when indexing a document fails."""


class SearchError(BusinessDocsError):
    """Raised when a search operation fails."""
