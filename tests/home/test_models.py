import pytest

from booster_home.context.compiler import ContextCompiler
from booster_home.models import ChatCompletionRequest, ModelProfile, SessionContext


@pytest.mark.asyncio
async def test_provider_reasoning_content_survives_compilation() -> None:
    request = ChatCompletionRequest(
        model="model",
        messages=[
            {"role": "user", "content": "continue"},
            {"role": "assistant", "content": "", "reasoning_content": "provider reasoning"},
        ],
    )
    result = await ContextCompiler().compile(
        request,
        SessionContext(session_id="reasoning"),
        ModelProfile(id="model"),
    )
    assert result.messages[-1].model_extra["reasoning_content"] == "provider reasoning"
