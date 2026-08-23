from booster_home.context.packer import ContextPacker
from booster_home.models import ContextBlock, ContextCategory, Priority


def test_packer_keeps_protected_blocks_and_order() -> None:
    blocks = [
        ContextBlock(
            category=ContextCategory.SYSTEM,
            role="system",
            priority=Priority.P0,
            content="rules",
            metadata={"message_index": 0},
        ),
        ContextBlock(
            category=ContextCategory.USER_TASK,
            role="user",
            priority=Priority.P0,
            content="task",
            metadata={"message_index": 1},
        ),
        ContextBlock(
            category=ContextCategory.ASSISTANT_RESPONSE,
            role="assistant",
            priority=Priority.P3,
            content="old",
            relevance=0.1,
            metadata={"message_index": 2},
        ),
    ]
    messages = ContextPacker().pack(blocks, max_tokens=20)
    assert [message.role for message in messages] == ["system", "user", "assistant"]
    assert [message.content for message in messages] == ["rules", "task", "old"]
