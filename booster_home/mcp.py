"""Control-plane MCP tools для уже созданного HomeRuntime.

Модуль не создаёт runtime сам: server.py или embedded host передаёт его через
dependency injection. Это не перехватывает OpenAI requests и не создаёт второй
индекс.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .research.store import ResearchInputError
from .runtime import HomeRuntime


def setup_home_tools(mcp: Any, runtime: HomeRuntime | None) -> None:
    """Регистрирует Home tools с явной диагностикой недоступного runtime."""

    def unavailable() -> dict[str, Any]:
        return {"error": "Booster Home runtime не подключён к этому MCP process"}

    async def ensure_runtime() -> HomeRuntime | None:
        if runtime is None:
            return None
        await runtime.start()
        return runtime

    @mcp.tool()
    async def home_status() -> dict[str, Any]:
        """Возвращает реальный redacted status Home runtime."""
        home_runtime = await ensure_runtime()
        return await home_runtime.status() if home_runtime is not None else unavailable()

    @mcp.tool()
    async def session_status(session_id: str) -> dict[str, Any]:
        """Возвращает timeline/working set одной session."""
        home_runtime = await ensure_runtime()
        if home_runtime is None:
            return unavailable()
        context = await home_runtime.session_store.context(session_id)
        return {
            "session_id": session_id,
            "working_set": context["working_set"],
            "recent_events": context["recent_events"],
        }

    @mcp.tool()
    async def context_stats(session_id: str) -> dict[str, Any]:
        """Возвращает число artifacts и timeline entries session."""
        home_runtime = await ensure_runtime()
        if home_runtime is None:
            return unavailable()
        artifacts = await home_runtime.artifact_store.list_metadata(session_id)
        events = await home_runtime.session_store.read_events(session_id, limit=1000)
        return {
            "session_id": session_id,
            "artifacts": len(artifacts),
            "timeline_events": len(events),
        }

    @mcp.tool()
    async def retrieve_session_artifact(
        session_id: str,
        artifact_ref: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> dict[str, Any]:
        """Восстанавливает exact raw artifact или заданный fragment."""
        home_runtime = await ensure_runtime()
        if home_runtime is None:
            return unavailable()
        if start_line is None:
            value = await home_runtime.artifact_store.retrieve(session_id, artifact_ref)
        else:
            value = await home_runtime.artifact_store.retrieve_fragment(
                session_id,
                artifact_ref,
                start_line=start_line,
                end_line=end_line,
            )
        return {"session_id": session_id, "artifact_ref": artifact_ref, "content": value}

    async def _delegate(
        task: str, role: str, context: str = "", model: str | None = None, repo: str | None = None
    ) -> dict[str, Any]:
        home_runtime = await ensure_runtime()
        if home_runtime is None or home_runtime.delegator is None:
            return unavailable()
        return await home_runtime.delegator.delegate_local(
            task, role=role, context=context, model=model, repo=repo
        )

    @mcp.tool()
    async def delegate_local(
        task: str,
        role: str = "worker",
        context: str = "",
        model: str | None = None,
        repo: str | None = None,
    ) -> dict[str, Any]:
        """Делегирует bounded task общему local WorkerPool."""
        return await _delegate(task, role, context, model, repo)

    @mcp.tool()
    async def local_code_review(
        task: str, context: str = "", model: str | None = None, repo: str | None = None
    ) -> dict[str, Any]:
        """Запускает роль review через общий WorkerPool."""
        return await _delegate(task, "review", context, model, repo)

    @mcp.tool()
    async def local_test_analysis(
        task: str, context: str = "", model: str | None = None, repo: str | None = None
    ) -> dict[str, Any]:
        """Запускает роль tests через общий WorkerPool."""
        return await _delegate(task, "tests", context, model, repo)

    @mcp.tool()
    async def local_log_analysis(
        task: str, context: str = "", model: str | None = None, repo: str | None = None
    ) -> dict[str, Any]:
        """Запускает роль logs через общий WorkerPool."""
        return await _delegate(task, "logs", context, model, repo)

    @mcp.tool()
    async def local_summarize(
        task: str, context: str = "", model: str | None = None, repo: str | None = None
    ) -> dict[str, Any]:
        """Запускает роль summarize через общий WorkerPool."""
        return await _delegate(task, "summarize", context, model, repo)

    async def research_service() -> Any:
        home_runtime = await ensure_runtime()
        if home_runtime is None or home_runtime.research is None:
            return None
        return home_runtime.research

    async def research_call(method: str, *args: Any, **kwargs: Any) -> dict[str, Any]:
        service = await research_service()
        if service is None:
            return unavailable()
        try:
            return await asyncio.to_thread(getattr(service, method), *args, **kwargs)
        except (ResearchInputError, ValueError) as exc:
            return {"error": str(exc)}

    @mcp.tool(name="booster.project_snapshot")
    async def project_snapshot(
        root: str | None = None,
        include: list[str] | None = None,
        max_tokens: int = 12_000,
        mode: str = "semantic",
    ) -> dict[str, Any]:
        """Собирает bounded project snapshot; binary checkpoints идут только metadata."""
        return await research_call(
            "project_snapshot", root=root, include=include, max_tokens=max_tokens, mode=mode
        )

    @mcp.tool(name="booster.experiment_state")
    async def experiment_state(
        project: str | None = None, max_tokens: int = 4_000, include_history: int = 6
    ) -> dict[str, Any]:
        """Возвращает научное состояние из research_state/memory/metrics."""
        return await research_call(
            "experiment_state",
            project=project,
            max_tokens=max_tokens,
            include_history=include_history,
        )

    @mcp.tool(name="booster.artifact_lookup")
    async def artifact_lookup(
        query: str,
        types: list[str] | None = None,
        top_k: int = 8,
        root: str | None = None,
    ) -> dict[str, Any]:
        """Ищет научные артефакты по содержимому и имени."""
        return await research_call(
            "artifact_lookup", query=query, types=types, top_k=top_k, root=root
        )

    @mcp.tool(name="booster.log_digest")
    async def log_digest(
        path: str,
        extract: list[str] | None = None,
        compare_to: str | None = None,
        root: str | None = None,
    ) -> dict[str, Any]:
        """Формирует структурированный scientific digest metrics/log файла."""
        return await research_call(
            "log_digest",
            path=path,
            extract=extract,
            compare_to=compare_to,
            root=root,
        )

    @mcp.tool(name="booster.compare_runs")
    async def compare_runs(
        runs: list[str],
        metrics: list[str],
        normalize_eval_regime: bool = True,
        root: str | None = None,
    ) -> dict[str, Any]:
        """Сравнивает runs и запрещает numeric comparison при regime mismatch."""
        return await research_call(
            "compare_runs",
            runs=runs,
            metrics=metrics,
            normalize_eval_regime=normalize_eval_regime,
            root=root,
        )

    @mcp.tool(name="booster.hypothesis_register")
    async def hypothesis_register(
        action: str = "record",
        hypothesis: str | None = None,
        status: str = "proposed",
        evidence_for: list[str] | None = None,
        evidence_against: list[str] | None = None,
        confounds: list[str] | None = None,
        confidence: float = 0.0,
        hypothesis_id: str | None = None,
        project: str | None = None,
        control_arms: list[str] | None = None,
        independent_variable: str | None = None,
        dependent_metrics: list[str] | None = None,
        pass_criteria: list[str] | None = None,
        fail_criteria: list[str] | None = None,
        required_artifacts: list[str] | None = None,
    ) -> dict[str, Any]:
        """Хранит научные гипотезы и evidence в research_state.json."""
        return await research_call(
            "hypothesis_register",
            action=action,
            hypothesis=hypothesis,
            status=status,
            evidence_for=evidence_for,
            evidence_against=evidence_against,
            confounds=confounds,
            confidence=confidence,
            hypothesis_id=hypothesis_id,
            project=project,
            control_arms=control_arms,
            independent_variable=independent_variable,
            dependent_metrics=dependent_metrics,
            pass_criteria=pass_criteria,
            fail_criteria=fail_criteria,
            required_artifacts=required_artifacts,
        )

    @mcp.tool(name="booster.next_experiment")
    async def next_experiment(
        hypothesis_id: str,
        constraints: dict[str, Any] | None = None,
        project: str | None = None,
    ) -> dict[str, Any]:
        """Собирает кандидатный experimental design из зарегистрированной гипотезы."""
        return await research_call(
            "next_experiment",
            hypothesis_id=hypothesis_id,
            constraints=constraints,
            project=project,
        )

    @mcp.tool(name="booster.context_pack")
    async def context_pack(
        task: str,
        budget_tokens: int = 16_000,
        sources: list[str] | None = None,
        exclude: list[str] | None = None,
        mode: str = "research",
        project: str | None = None,
    ) -> dict[str, Any]:
        """Собирает context layers L0..L4 для coding/debug/research задач."""
        return await research_call(
            "context_pack",
            task=task,
            budget_tokens=budget_tokens,
            sources=sources,
            exclude=exclude,
            mode=mode,
            project=project,
        )

    @mcp.tool(name="booster.worker_delegate")
    async def worker_delegate(
        role: str,
        model: str | None,
        task: str,
        context_budget: int = 8_000,
        output_budget: int = 1_500,
        context: str = "",
        project: str | None = None,
    ) -> dict[str, Any]:
        """Делегирует ограниченную задачу одной из research worker ролей."""
        service = await research_service()
        if service is None:
            return unavailable()
        try:
            return await service.worker_delegate(
                role=role,
                model=model,
                task=task,
                context_budget=context_budget,
                output_budget=output_budget,
                context=context,
                project=project,
            )
        except ResearchInputError as exc:
            return {"error": str(exc)}

    @mcp.tool(name="booster.checkpoint_registry")
    async def checkpoint_registry(
        action: str,
        path: str | None = None,
        experiment: str | None = None,
        parent: str | None = None,
        step: int | None = None,
        status: str | None = None,
        keep: bool | None = None,
        branch: str | None = None,
        criteria: dict[str, Any] | None = None,
        project: str | None = None,
    ) -> dict[str, Any]:
        """Регистрирует checkpoint metadata и выдаёт KEEP/delete candidates."""
        return await research_call(
            "checkpoint_registry",
            action=action,
            path=path,
            experiment=experiment,
            parent=parent,
            step=step,
            status=status,
            keep=keep,
            branch=branch,
            criteria=criteria,
            project=project,
        )

    @mcp.tool(name="booster.lightning_trace")
    async def lightning_trace(
        prompt: str,
        target_mode: str = "next_token",
        checkpoint: str | None = None,
        trace: list[str] | None = None,
        human_labels: bool = True,
        project: str | None = None,
    ) -> dict[str, Any]:
        """Возвращает существующий LightningField trace для визуализации."""
        return await research_call(
            "lightning_trace",
            prompt=prompt,
            target_mode=target_mode,
            checkpoint=checkpoint,
            trace=trace,
            human_labels=human_labels,
            project=project,
        )
