"""OpenAI-compatible backend для semantic workers."""

from __future__ import annotations

import hashlib
from typing import Protocol

from ..models import WorkerJob, WorkerResult
from ..routing import ModelRouter, RoutingError
from ..upstream.provider import UpstreamProvider
from .cache import WorkerCache
from .prompts import build_prompt
from .schemas import WorkerPayload, parse_worker_payload


class ContextWorkerBackend(Protocol):
    """Контракт semantic worker."""

    async def execute(self, job: WorkerJob) -> WorkerResult: ...


class OpenAICompatibleWorkerBackend:
    """Использует тот же provider/http client, что и gateway runtime."""

    def __init__(
        self,
        provider: UpstreamProvider,
        default_model: str,
        *,
        router: ModelRouter | None = None,
        cache: WorkerCache[WorkerResult] | None = None,
        repair_attempts: int = 1,
    ) -> None:
        self.provider = provider
        self.default_model = default_model
        self.router = router
        self.cache = cache or WorkerCache(256)
        self.repair_attempts = min(1, max(0, repair_attempts))

    def _model(self, job: WorkerJob) -> str:
        if job.model:
            return job.model
        if self.router is not None:
            try:
                return self.router.choose(job.channel).model
            except RoutingError:
                raise
        return self.default_model

    @staticmethod
    def _cache_key(job: WorkerJob, model: str) -> str:
        output_budget = job.metadata.get("max_output_tokens")
        payload = (
            f"{job.prompt_version}|{job.schema_version}|{model}|{job.task}|"
            f"{job.channel}|{output_budget}|{job.content}"
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @staticmethod
    def _extract_content(response: dict[str, object]) -> str:
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ValueError("worker response не содержит choices")
        message = choices[0].get("message")
        if not isinstance(message, dict):
            raise ValueError("worker response не содержит message")
        content = message.get("content")
        if isinstance(content, str) and content.strip():
            return content
        # Nemotron и некоторые reasoning providers используют это поле.
        reasoning = message.get("reasoning_content")
        if isinstance(reasoning, str) and reasoning.strip():
            return reasoning
        raise ValueError("worker response не содержит content/reasoning_content")

    async def _request(self, job: WorkerJob, model: str, *, repair: bool = False) -> WorkerPayload:
        prompt = build_prompt(job)
        if repair:
            prompt.append(
                {
                    "role": "user",
                    "content": "Исправь только JSON предыдущего ответа. Верни один JSON object.",
                }
            )
        requested_output = job.metadata.get("max_output_tokens")
        max_tokens = (
            max(1, min(int(requested_output), 8192))
            if isinstance(requested_output, int) and requested_output > 0
            else 1024
        )
        payload = {
            "model": model,
            "messages": prompt,
            "temperature": 0,
            "max_tokens": max_tokens,
            "response_format": {"type": "json_object"},
            "stream": False,
        }
        response = await self.provider.chat_completions(payload)
        return parse_worker_payload(self._extract_content(response))

    async def execute(self, job: WorkerJob) -> WorkerResult:
        model = self._model(job)
        key = self._cache_key(job, model)
        cached = self.cache.get(key)
        if cached is not None:
            return cached.model_copy()
        try:
            payload = await self._request(job, model)
        except Exception as first_error:
            if self.repair_attempts <= 0:
                return WorkerResult(
                    job_id=job.id,
                    channel=job.channel,
                    status="invalid",
                    observed=[job.content[:2000]],
                    reason="worker output invalid or unavailable",
                )
            try:
                payload = await self._request(job, model, repair=True)
            except Exception as second_error:
                return WorkerResult(
                    job_id=job.id,
                    channel=job.channel,
                    status="deterministic",
                    observed=[job.content[:2000]],
                    reason=f"controlled repair failed: {type(second_error).__name__}",
                    raw_fields={"first_error": type(first_error).__name__},
                )
        result = WorkerResult(
            job_id=job.id,
            channel=job.channel,
            status="success",
            observed=payload.observed + payload.critical + payload.new + payload.changed,
            inferred=payload.inferred + payload.suspected_root_causes,
            uncertain=payload.uncertain,
            summary=payload.summary,
            raw_fields=payload.model_extra or {},
        )
        self.cache.set(key, result)
        return result
