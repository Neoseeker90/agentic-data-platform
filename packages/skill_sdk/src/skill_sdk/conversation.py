from __future__ import annotations


def build_contextual_request(request_text: str, history: list[dict]) -> str:
    """Prepend conversation history to the current request text.

    Only include history if there are prior turns. Format:

    [Conversation history]
    User: ...
    Assistant: ...
    User: ...
    Assistant: ...

    Current request: {request_text}
    """
    if not history:
        return request_text

    role_label = {"user": "User", "assistant": "Assistant"}
    lines = ["[Conversation history]"]
    for turn in history:
        label = role_label.get(turn["role"], turn["role"].capitalize())
        lines.append(f"{label}: {turn['content']}")

    lines.append("")
    lines.append(f"Current request: {request_text}")
    return "\n".join(lines)
