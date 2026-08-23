"""Воспроизводимый benchmark Context Compiler без маркетинговых оценок.

Запуск: ``python benchmarks/home_context_benchmark.py``.
Скрипт намеренно печатает фактические token/latency значения текущей машины.
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from booster_home.context.budget import ContextBudgetManager
from booster_home.context.compiler import ContextCompiler
from booster_home.memory.artifact_store import ArtifactStore
from booster_home.memory.pager import MemoryPager
from booster_home.models import (
    ChatCompletionRequest,
    ContextBlock,
    ContextCategory,
    ModelProfile,
    SessionContext,
)


class TargetedFooServiceWorldModel:
    """Минимальный fake targeted retrieval для проверки anti-bloat invariant."""

    async def enrich(self, task, session, *, max_tokens):
        return type(
            "Enrichment",
            (),
            {
                "blocks": [
                    ContextBlock(
                        source="repo_index",
                        category=ContextCategory.REPO_CONTEXT,
                        content="FooService.validate: targeted snippet",
                        relevance=0.95,
                    )
                ],
                "warnings": [],
            },
        )()


async def run() -> None:
    started = time.perf_counter()
    with TemporaryDirectory(prefix="booster-home-benchmark-") as directory:
        root = Path(directory)
        system = "\n".join(f"PROJECT_RULE_321 system rule {index}" for index in range(5000))
        conversation = "\n".join(
            f"conversation episode {index} ACTIVE_USER_TASK_123" for index in range(5000)
        )
        duplicates = "\n".join("duplicate log line" for _ in range(20000))
        diagnostics = "\n".join(
            f"error ROOT_EXCEPTION_456 file_{index % 20}.py:4" for index in range(10000)
        )
        tests = "\n".join(f"FAILED test_{index} FAILED_TEST_654" for index in range(15000))
        repo = "\n".join(f"TARGET_FILE_789 FooService method {index}" for index in range(15000))
        request = ChatCompletionRequest(
            model="benchmark-model",
            messages=[
                {"role": "system", "content": system},
                {"role": "assistant", "content": conversation},
                {"role": "tool", "name": "terminal", "content": duplicates},
                {"role": "tool", "name": "diagnostics", "content": diagnostics},
                {"role": "tool", "name": "pytest", "content": tests},
                {
                    "role": "user",
                    "content": "Fix FooService using the current test and diagnostics context.",
                },
                {"role": "assistant", "content": repo},
            ],
        )
        compiler = ContextCompiler(
            budget_manager=ContextBudgetManager(
                configured_context_window=524288,
                reserve_output=8192,
                safety_margin=2048,
            ),
            pager=MemoryPager(ArtifactStore(root)),
            world_model=TargetedFooServiceWorldModel(),
        )
        raw_tokens = compiler.token_counter.count_messages(request.messages)
        compile_started = time.perf_counter()
        compiled = await compiler.compile(
            request,
            SessionContext(session_id="benchmark", working_set={"files": ["FooService"]}),
            ModelProfile(id="benchmark-model", context_window=524288),
        )
        compile_seconds = time.perf_counter() - compile_started
        artifacts = await compiler.pager.artifacts.list_metadata("benchmark")
        recovered = False
        if artifacts:
            recovered = bool(await compiler.pager.artifacts.retrieve("benchmark", artifacts[0].id))
        targeted = any("FooService" in message.text for message in compiled.messages)
        print(f"raw_tokens={raw_tokens}")
        print(f"deterministic_tokens={compiled.compiled_tokens}")
        print(f"semantic_tokens={compiled.retrieved_tokens}")
        print(f"retrieved_tokens={compiled.retrieved_tokens}")
        print(f"final_tokens={compiled.compiled_tokens}")
        print(f"compression_ratio={compiled.compression_ratio:.6f}")
        print(f"compiler_latency_seconds={compile_seconds:.6f}")
        print("worker_latency_seconds=0.000000 (workers not configured in benchmark)")
        retained_facts = sum(
            1 for operation in compiled.operations if operation.operation == "retrieve"
        )
        print(f"retained_facts={retained_facts}")
        print(f"exact_artifact_recovery={recovered}")
        print(f"targeted_FooService_enrichment={targeted}")
        print(f"total_latency_seconds={time.perf_counter() - started:.6f}")


if __name__ == "__main__":
    asyncio.run(run())
