import hashlib
from pathlib import Path


class PromptLoader:
    """Loads, versions, and renders versioned prompt templates from disk."""

    def __init__(self, prompts_dir: Path | None = None) -> None:
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent.parent / "prompts"
        self._prompts_dir = prompts_dir

    def load(self, name: str) -> str:
        """Read and return the raw contents of {prompts_dir}/{name}.md.

        Raises FileNotFoundError with a descriptive message if the file is missing.
        """
        path = self._prompts_dir / f"{name}.md"
        if not path.exists():
            raise FileNotFoundError(f"Prompt template '{name}' not found. Expected file at: {path}")
        return path.read_text(encoding="utf-8")

    def get_version_id(self, name: str) -> str:
        """Return the SHA-256 hex digest of the prompt file contents."""
        contents = self.load(name)
        return hashlib.sha256(contents.encode("utf-8")).hexdigest()

    def render(self, name: str, **kwargs: str) -> str:
        """Load the prompt and substitute kwargs via str.format_map."""
        template = self.load(name)
        return template.format_map(kwargs)
