class MemoryError(Exception):
    """Base exception for all memory operations."""

class EmbeddingError(MemoryError):
    """Raised when embedding generation fails (provider error, bad input, wrong dimension)."""

class MemoryStoreError(MemoryError):
    """Raised when storing memory fails."""

class MemorySearchError(MemoryError):
    """Raised when searching memory fails."""

class MemorySecretError(MemoryError):
    """Raised when content looks like it contains a secret/credential."""
