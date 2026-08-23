"""Проверки research coprocessor и его safety guarantees."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Mapping

from fastmcp import FastMCP

from booster_home.context.budget import ContextBudgetManager
from booster_home.context.compiler import ContextCompiler
from booster_home.mcp import setup_home_tools
from booster_home.memory.pager import ContextIntegrityError
from booster_home.models import ChatCompletionRequest, ContextPolicy, ModelProfile, WorkerJob
from booster_home.research.service import ResearchService
from booster_home.upstream.provider import UpstreamProvider
from booster_home.workers.client import OpenAICompatibleWorkerBackend


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")


def test_project_snapshot_keeps_checkpoint_metadata_only(tmp_path: Path) -> None:
    checkpoint = tmp_path / "hypr_v20_step500.pt"
    checkpoint.write_bytes(b"BINARY-CHECKPOINT-SECRET")
    (tmp_path / "hypr_v20_step500.pt.json").write_text(
        json.dumps(
            {
                "step": 500,
                "base_checkpoint": "v20_base.pt",
                "trainable_groups": ["substrate", "readout"],
                "metrics": {"CE": 4.87},
                "parent_experiment": "v19",
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "v20_metrics.jsonl").write_text('{"step": 500, "CE": 4.87}\n', encoding="utf-8")

    result = ResearchService(tmp_path).project_snapshot(
        include=["*.pt metadata only", "*metrics*.jsonl"], max_tokens=1200
    )

    assert result["binary_content_included"] is False
    assert result["checkpoints"][0]["step"] == 500
    assert result["checkpoints"][0]["trainable_groups"] == ["substrate", "readout"]
    assert "BINARY-CHECKPOINT-SECRET" not in json.dumps(result)
    assert all(
        "content" not in item for item in result["files"] if item["kind"] == "checkpoint_metadata"
    )


def test_experiment_state_and_next_experiment_use_local_state(tmp_path: Path) -> None:
    (tmp_path / "research_state.json").write_text(
        json.dumps(
            {
                "project": "HYPR-LIGHTNING",
                "current_baseline": {"run": "v20", "CE": 4.87},
                "current_best_result": {"run": "v26", "CE": 4.12},
                "known_confounds": ["forcing_budget"],
                "frozen_assumptions": ["same tokenizer"],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "memory_bank.md").write_text(
        "# Research\n- baseline is v20\n- confound: forcing budget\n", encoding="utf-8"
    )
    service = ResearchService(tmp_path)
    recorded = service.hypothesis_register(
        hypothesis="late forcing redirects attractor near settling",
        status="partially_supported",
        evidence_for=["v26"],
        evidence_against=["v28"],
        confounds=["forcing_budget"],
        confidence=0.45,
    )

    state = service.experiment_state(include_history=6)
    candidate = service.next_experiment(
        recorded["hypothesis"]["id"],
        {"max_steps": 500, "gpu": "RTX3060", "max_vram_gb": 11.5, "runtime": "triton"},
    )

    assert state["current_baseline"]["run"] == "v20"
    assert state["current_best_result"]["run"] == "v26"
    assert state["known_confounds"] == ["forcing_budget"]
    assert candidate["control_arms"] == ["baseline", "candidate"]
    assert candidate["constraints"]["max_steps"] == 500
    assert candidate["source_hypothesis"]["id"] == "H-001"


def test_log_digest_and_compare_runs_reject_regime_mismatch(tmp_path: Path) -> None:
    _write_jsonl(
        tmp_path / "v26_metrics.jsonl",
        [
            {"step": 1, "eval_regime": "standard", "CE": 5.0, "heldout": 5.2, "entropy": 1.0},
            {"step": 2, "eval_regime": "standard", "CE": 4.0, "heldout": 4.4, "entropy": 1.1},
        ],
    )
    _write_jsonl(
        tmp_path / "v29_metrics.jsonl",
        [
            {"step": 1, "eval_regime": "different", "CE": 11.0, "heldout": 11.2},
            {"step": 2, "eval_regime": "different", "CE": 11.04, "heldout": 11.3},
        ],
    )
    service = ResearchService(tmp_path)

    digest = service.log_digest("v26_metrics.jsonl", extract=["loss_trend", "heldout_trend"])
    comparison = service.compare_runs(["v26_metrics.jsonl", "v29_metrics.jsonl"], ["CE", "heldout"])

    assert {
        "OBSERVED",
        "INCREASED",
        "DECREASED",
        "UNCHANGED",
        "ANOMALIES",
        "POSSIBLE_CONFOUNDS",
    } <= digest.keys()
    assert digest["DECREASED"][0]["metric"] == "loss_trend"
    assert comparison["status"] == "NOT DIRECTLY COMPARABLE"
    assert comparison["comparisons"] == {}
    assert "NOT DIRECTLY COMPARABLE" in comparison["warnings"][0]


def test_artifact_lookup_checkpoint_registry_and_lightning_trace(tmp_path: Path) -> None:
    checkpoint = tmp_path / "hypr_v29_substrate_final.pt"
    checkpoint.write_bytes(b"DO-NOT-READ")
    intermediate = tmp_path / "hypr_v28_intermediate.pt"
    intermediate.write_bytes(b"INTERMEDIATE")
    (tmp_path / "hypr_v29_substrate_final.pt.trace.jsonl").write_text(
        json.dumps(
            {
                "token": "lightning",
                "target": "field",
                "step": 17,
                "selected_nodes": [1, 2],
                "candidate_nodes": [1, 2, 3],
                "energy": 0.42,
                "target_rank": 1,
                "route_regret": 0.1,
                "state_drift": 0.03,
                "semantic_labels": ["settling", "frontier"],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "v29_report.json").write_text(
        json.dumps({"experiment": "v29", "status": "failed", "late_forcing": True}),
        encoding="utf-8",
    )
    service = ResearchService(tmp_path)
    service.checkpoint_registry(
        "register",
        "hypr_v29_substrate_final.pt",
        experiment="v29",
        status="failed",
        keep=False,
        branch="HYPR",
    )
    service.checkpoint_registry(
        "register",
        "hypr_v28_intermediate.pt",
        experiment="v28",
        status="failed",
        keep=False,
        branch="HYPR",
    )
    service.checkpoint_registry(
        "register",
        "hypr_v29_substrate_final.pt",
        experiment="v29",
        status="baseline",
        keep=True,
        branch="HYPR",
    )

    lookup = service.artifact_lookup("late forcing failed v29", ["json"], top_k=4)
    registry = service.checkpoint_registry("find", criteria={"branch": "HYPR"})
    trace = service.lightning_trace(
        "lightning field prompt", checkpoint="hypr_v29_substrate_final.pt", human_labels=True
    )

    assert lookup["results"][0]["path"] == "v29_report.json"
    assert registry["KEEP"][0]["path"] == "hypr_v29_substrate_final.pt"
    assert registry["DELETE_CANDIDATES"][0]["path"] == "hypr_v28_intermediate.pt"
    assert trace["status"] == "ok"
    assert trace["records"][0]["target_rank"] == 1
    assert "DO-NOT-READ" not in json.dumps(trace)


def test_context_pack_has_layers_budget_and_no_binary_content(tmp_path: Path) -> None:
    (tmp_path / "SPEC.md").write_text("runtime contract\n" * 40, encoding="utf-8")
    source_dir = tmp_path / "src"
    source_dir.mkdir()
    (source_dir / "train.py").write_text(
        "def train_v30():\n    return 'joint substrate readout'\n", encoding="utf-8"
    )
    (tmp_path / "checkpoint.pt").write_bytes(b"BINARY")

    result = ResearchService(tmp_path).context_pack(
        "implement v30 joint substrate-readout training",
        budget_tokens=512,
        sources=["current_experiment", "relevant_code", "runtime_contract"],
    )

    assert result["tokens"] <= 512
    assert result["layers"][0]["layer"] == "L0"
    assert {item["layer"] for item in result["layers"]} <= {"L0", "L1", "L2", "L3", "L4"}
    assert "BINARY" not in result["context"]
    assert result["binary_content_included"] is False


def test_research_mcp_tool_names_are_explicit() -> None:
    mcp = FastMCP("research-test")
    setup_home_tools(mcp, None)
    tools = asyncio.run(mcp.list_tools())
    names = {tool.name for tool in tools}
    assert {
        "booster.project_snapshot",
        "booster.experiment_state",
        "booster.artifact_lookup",
        "booster.log_digest",
        "booster.compare_runs",
        "booster.hypothesis_register",
        "booster.next_experiment",
        "booster.context_pack",
        "booster.worker_delegate",
        "booster.checkpoint_registry",
        "booster.lightning_trace",
    } <= names


class _WorkerProvider(UpstreamProvider):
    def __init__(self) -> None:
        self.payloads: list[Mapping[str, Any]] = []

    async def models(self):
        raise NotImplementedError

    async def chat_completions(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        self.payloads.append(payload)
        return {"choices": [{"message": {"content": '{"summary":"ok"}'}}]}

    async def chat_completions_stream(self, payload: Mapping[str, Any]):
        raise NotImplementedError

    async def responses(self, payload: Mapping[str, Any]):
        raise NotImplementedError

    async def responses_stream(self, payload: Mapping[str, Any]):
        raise NotImplementedError

    async def close(self) -> None:
        return None


def test_worker_output_budget_is_forwarded() -> None:
    provider = _WorkerProvider()
    backend = OpenAICompatibleWorkerBackend(provider, "worker")
    result = asyncio.run(
        backend.execute(
            WorkerJob(
                channel="log_analyst",
                content="find anomalies",
                metadata={"max_output_tokens": 1500},
            )
        )
    )

    assert result.status == "success"
    assert provider.payloads[0]["max_tokens"] == 1500


def test_policy_off_still_fails_on_known_hard_budget(tmp_path: Path) -> None:
    compiler = ContextCompiler(
        policy=ContextPolicy.OFF,
        budget_manager=ContextBudgetManager(
            configured_context_window=128, reserve_output=16, safety_margin=8
        ),
    )
    request = ChatCompletionRequest(
        model="fake",
        messages=[{"role": "user", "content": "too large " * 100}],
    )

    try:
        asyncio.run(
            compiler.compile(
                request,
                {"session_id": "s"},
                ModelProfile(id="fake", context_window=128),
            )
        )
    except ContextIntegrityError:
        return
    raise AssertionError("policy off должен сохранять hard budget integrity")
