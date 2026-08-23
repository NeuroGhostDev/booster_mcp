"""API helper models и Responses translation."""

from __future__ import annotations

from typing import Any

from ..models import Message

_TEXT_PART_TYPES = {"input_text", "text", "output_text"}


def _text_content(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        raise ValueError("Responses text content должен быть string или list")
    parts: list[str] = []
    for part in value:
        if not isinstance(part, dict) or part.get("type") not in _TEXT_PART_TYPES:
            raise ValueError("неподдерживаемый Responses content part")
        parts.append(str(part.get("text", "")))
    return "\n".join(parts)


def responses_input_to_messages(value: Any) -> list[Message]:
    """Поддерживает string и стандартные message/input_text формы Responses."""
    if isinstance(value, str):
        return [Message(role="user", content=value)]
    if not isinstance(value, list):
        raise ValueError("Responses input должен быть string или list")
    messages: list[Message] = []
    for item in value:
        if isinstance(item, str):
            messages.append(Message(role="user", content=item))
            continue
        if not isinstance(item, dict):
            raise ValueError("Responses input item должен быть object")
        if isinstance(item.get("role"), str):
            content = _text_content(item.get("content", ""))
            messages.append(Message.model_validate({**item, "content": content}))
            continue
        if item.get("type") in {"message", "input_text"}:
            content = _text_content(item.get("content", item.get("text", "")))
            messages.append(Message(role=str(item.get("role", "user")), content=content))
            continue
        raise ValueError("неподдерживаемая Responses input form")
    return messages


def messages_to_responses_input(messages: list[Message]) -> list[dict[str, Any]]:
    return [
        {
            "role": message.role,
            "content": [{"type": "input_text", "text": message.text}],
            **({"name": message.name} if message.name else {}),
        }
        for message in messages
    ]


def chat_response_to_responses(value: dict[str, Any]) -> dict[str, Any]:
    """Делает минимальный Responses envelope, сохраняя upstream extra fields."""
    result = dict(value)
    result["object"] = "response"
    choices = value.get("choices")
    output: list[dict[str, Any]] = []
    if isinstance(choices, list):
        for choice in choices:
            if not isinstance(choice, dict):
                continue
            message = choice.get("message", {})
            if isinstance(message, dict):
                output.append(
                    {
                        "type": "message",
                        "role": message.get("role", "assistant"),
                        "content": [
                            {
                                "type": "output_text",
                                "text": message.get("content")
                                or message.get("reasoning_content", ""),
                            }
                        ],
                    }
                )
    result["output"] = output
    result.pop("choices", None)
    return result
