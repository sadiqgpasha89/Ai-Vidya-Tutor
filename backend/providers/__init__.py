"""Model providers. The rest of the app talks only to the small interface defined here."""
from __future__ import annotations

from typing import Callable, Iterator

# (tool name, tool input) -> (result text, is_error)
ToolRunner = Callable[[str, object], "tuple[str, bool]"]


class ProviderError(Exception):
    """An error whose message is already safe and helpful to show a student/teacher."""


class Preempted(Exception):
    """Background work stopped early because a student is waiting for the model."""


class Provider:
    name = "base"
    # True when the model is small enough that each lesson section is better generated in its own call.
    per_section = False
    # True when quiz answer keys should be double-checked by an independent solve (small models make wrong keys).
    verify_quizzes = False

    def health(self) -> dict:
        """-> {"ready": bool, "problem": str | None}"""
        raise NotImplementedError

    def stream_text(self, system: str, user: str, effort: str, role: str = "lesson", should_stop: Callable[[], bool] | None = None) -> Iterator[str]:
        raise NotImplementedError

    def structured(self, system: str, user: str, schema: dict, effort: str, max_tokens: int = 4000, role: str = "quiz") -> dict:
        raise NotImplementedError

    def agent(self, system_blocks: list[dict], history: list[dict], tools: list[dict], run_tool: ToolRunner, model: str | None = None) -> Iterator[dict]:
        """Tool-using conversation turn. Yields {"type": "text", "delta"}, {"type": "tool", "name"} and
        {"type": "_tools_ran"} (after each batch of tool executions, so the caller can flush UI events)."""
        raise NotImplementedError

    def vision(self, system: str, user: str, images_b64: list[str]) -> str:
        """Describe / transcribe images (homework photos, diagrams). Returns plain text."""
        raise NotImplementedError

    def friendly_error(self, exc: Exception) -> str:
        if isinstance(exc, ProviderError):
            return str(exc)
        return "Something went wrong while preparing the answer. Please try again."
