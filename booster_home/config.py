"""Конфигурация Booster Home с детерминированным precedence."""

from __future__ import annotations

import copy
import ipaddress
import os
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .models import ContextPolicy
from .telemetry.logging import redact_endpoint


class _ConfigModel(BaseModel):
    """Конфигурационные модели допускают новые provider-specific поля."""

    model_config = ConfigDict(extra="allow", validate_assignment=True)


def _local_bind(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value)
        return address.is_loopback
    except ValueError:
        return value.lower() in {"localhost", "localhost.localdomain"}


class HomeSettings(_ConfigModel):
    listen: str = "127.0.0.1"
    port: int = 7777
    verbose: bool = False
    json_logs: bool = False
    auth_token: str | None = Field(default_factory=lambda: os.getenv("BOOSTER_HOME_AUTH_TOKEN"))

    @field_validator("auth_token", mode="before")
    @classmethod
    def normalize_auth_token(cls, value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ValueError("auth_token должен быть строкой")
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_network(self) -> "HomeSettings":
        if not self.listen.strip():
            raise ValueError("listen не может быть пустым")
        if not 1 <= self.port <= 65535:
            raise ValueError("port должен находиться в диапазоне 1..65535")
        token = self.auth_token
        if token is not None and len(token) < 16:
            raise ValueError("auth_token должен содержать минимум 16 символов")
        if not _local_bind(self.listen) and token is None:
            raise ValueError("для non-loopback listen требуется home.auth_token")
        return self


class UpstreamSettings(_ConfigModel):
    type: str = "openai-compatible"
    base_url: str = "http://127.0.0.1:1234/v1"
    model: str = "nvidia/nemotron-3-nano-4b"
    api_key: str | None = None
    connect_timeout: float = 10.0
    read_timeout: float = 300.0
    max_retries: int = 2
    retry_backoff: float = 0.25

    @model_validator(mode="after")
    def validate_upstream(self) -> "UpstreamSettings":
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("upstream.base_url должен использовать http:// или https://")
        if self.connect_timeout <= 0 or self.read_timeout <= 0:
            raise ValueError("таймауты upstream должны быть положительными")
        if self.max_retries < 0 or self.max_retries > 8:
            raise ValueError("max_retries должен находиться в диапазоне 0..8")
        if self.retry_backoff < 0:
            raise ValueError("retry_backoff не может быть отрицательным")
        return self


class ContextSettings(_ConfigModel):
    policy: ContextPolicy = ContextPolicy.ADAPTIVE
    context_window: int | Literal["auto"] = "auto"
    reserve_output: int = 4096
    safety_margin: int = 1024
    soft_target_ratio: float = 0.55
    hard_target_ratio: float = 0.80
    compiler_timeout: float = 30.0
    persistent_memory: bool = True
    semantic_compression: bool = True
    semantic_enrichment: bool = True
    raw_artifacts: bool = True

    @model_validator(mode="after")
    def validate_context(self) -> "ContextSettings":
        if isinstance(self.context_window, int) and self.context_window <= 0:
            raise ValueError("context_window должен быть положительным или auto")
        if self.reserve_output <= 0:
            raise ValueError("reserve_output должен быть положительным")
        if self.safety_margin < 0:
            raise ValueError("safety_margin не может быть отрицательным")
        if not 0 < self.soft_target_ratio <= 1:
            raise ValueError("soft_target_ratio должен находиться в диапазоне (0, 1]")
        if not 0 < self.hard_target_ratio <= 1:
            raise ValueError("hard_target_ratio должен находиться в диапазоне (0, 1]")
        if self.hard_target_ratio < self.soft_target_ratio:
            raise ValueError("hard_target_ratio не может быть меньше soft_target_ratio")
        if self.compiler_timeout <= 0:
            raise ValueError("compiler_timeout должен быть положительным")
        if isinstance(self.context_window, int):
            if self.reserve_output + self.safety_margin >= self.context_window:
                raise ValueError("reserve_output и safety_margin оставляют нулевой input budget")
        return self


class WorkerSettings(_ConfigModel):
    model: str | None = None
    max_concurrency: int | Literal["auto"] = "auto"
    timeout_seconds: float = 60.0
    repair_attempts: int = 1
    cache_size: int = 256

    @model_validator(mode="after")
    def validate_workers(self) -> "WorkerSettings":
        if isinstance(self.max_concurrency, int) and self.max_concurrency <= 0:
            raise ValueError("workers.max_concurrency должен быть положительным или auto")
        if self.timeout_seconds <= 0:
            raise ValueError("workers.timeout_seconds должен быть положительным")
        if self.repair_attempts not in (0, 1):
            raise ValueError("repair_attempts ограничен значением 0 или 1")
        if self.cache_size < 0:
            raise ValueError("cache_size не может быть отрицательным")
        return self


class MemorySettings(_ConfigModel):
    root_dir: Path | None = None
    compression: str = "zstd"
    max_session_age_days: int = 30
    maintenance_interval_seconds: float = 60.0

    @model_validator(mode="after")
    def validate_memory(self) -> "MemorySettings":
        if self.max_session_age_days <= 0:
            raise ValueError("max_session_age_days должен быть положительным")
        if self.maintenance_interval_seconds <= 0:
            raise ValueError("maintenance_interval_seconds должен быть положительным")
        if self.compression not in {"zstd", "zlib", "none"}:
            raise ValueError("compression должен быть zstd, zlib или none")
        return self


class RoutingModel(_ConfigModel):
    id: str
    roles: set[str] = Field(default_factory=set)
    capabilities: set[str] = Field(default_factory=set)


class RoutingSettings(_ConfigModel):
    enabled: bool = False
    models: list[RoutingModel] = Field(default_factory=list)


class TelemetrySettings(_ConfigModel):
    enabled: bool = False


class ResearchSettings(_ConfigModel):
    """Bounded defaults research coprocessor-а."""

    global_context_budget: int = 16_000
    state_budget: int = 4_000
    code_retrieval_budget: int = 8_000
    logs_budget: int = 4_000
    worker_output_budget: int = 1_500
    artifact_top_k: int = 8
    history_depth: int = 5
    raw_log_threshold_bytes: int = 50_000
    duplicate_similarity_cutoff: float = 0.92
    binary_file_content: bool = False
    checkpoint_metadata: bool = True

    @model_validator(mode="after")
    def validate_research(self) -> "ResearchSettings":
        positive = {
            "global_context_budget": self.global_context_budget,
            "state_budget": self.state_budget,
            "code_retrieval_budget": self.code_retrieval_budget,
            "logs_budget": self.logs_budget,
            "worker_output_budget": self.worker_output_budget,
            "artifact_top_k": self.artifact_top_k,
            "history_depth": self.history_depth,
            "raw_log_threshold_bytes": self.raw_log_threshold_bytes,
        }
        if any(value <= 0 for value in positive.values()):
            raise ValueError("research budgets and limits must be positive")
        if not 0 < self.duplicate_similarity_cutoff <= 1:
            raise ValueError("duplicate_similarity_cutoff должен находиться в диапазоне (0, 1]")
        if self.binary_file_content:
            raise ValueError("binary_file_content должен быть false: binary content запрещён")
        if not self.checkpoint_metadata:
            raise ValueError("checkpoint_metadata должен быть true")
        return self


class HomeConfig(_ConfigModel):
    """Собранная конфигурация с удобными aliases для CLI и status."""

    home: HomeSettings = Field(default_factory=HomeSettings)
    upstream: UpstreamSettings = Field(default_factory=UpstreamSettings)
    context: ContextSettings = Field(default_factory=ContextSettings)
    workers: WorkerSettings = Field(default_factory=WorkerSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    routing: RoutingSettings = Field(default_factory=RoutingSettings)
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    research: ResearchSettings = Field(default_factory=ResearchSettings)
    project: Path | None = None
    no_persist: bool = False
    probe_generation: bool = False
    config_sources: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_flat_values(cls, value: Any) -> Any:
        """Принимает и nested TOML, и удобный flat constructor для tests/tools."""
        if not isinstance(value, dict):
            return value
        normalized = dict(value)
        sections = {
            "listen": "home",
            "port": "home",
            "verbose": "home",
            "json_logs": "home",
            "auth_token": "home",
            "base_url": "upstream",
            "model": "upstream",
            "api_key": "upstream",
            "context_window": "context",
            "reserve_output": "context",
            "context_policy": "context",
            "workers": "workers",
        }
        for key, section in sections.items():
            if key not in normalized:
                continue
            if section == key:
                # `workers=WorkerSettings(...)` уже является nested value;
                # только scalar form трактуем как CLI-like concurrency.
                if isinstance(normalized[key], BaseModel):
                    continue
                if isinstance(normalized[key], dict):
                    continue
                normalized[key] = {"max_concurrency": normalized[key]}
                continue
            section_value = normalized.get(section)
            if isinstance(section_value, BaseModel):
                section_value = section_value.model_dump()
            elif not isinstance(section_value, dict):
                section_value = {}
            target = (
                "policy"
                if key == "context_policy"
                else ("max_concurrency" if key == "workers" else key)
            )
            normalized[section] = {**section_value, target: normalized.pop(key)}
        return normalized

    @property
    def listen(self) -> str:
        return self.home.listen

    @property
    def port(self) -> int:
        return self.home.port

    @property
    def base_url(self) -> str:
        return self.upstream.base_url

    @property
    def model(self) -> str:
        return self.upstream.model

    @property
    def api_key(self) -> str | None:
        return self.upstream.api_key

    @property
    def effective_persistence(self) -> bool:
        return self.context.persistent_memory and not self.no_persist

    def redacted(self) -> dict[str, Any]:
        """Возвращает status-safe config без API key и секретов."""
        data = self.model_dump(mode="json")
        api_key = data.get("upstream", {}).get("api_key")
        data["upstream"]["api_key"] = "***configured***" if api_key else None
        endpoint = str(data["upstream"].get("base_url", ""))
        data["upstream"]["base_url"] = redact_endpoint(endpoint)
        auth_token = data.get("home", {}).get("auth_token")
        data["home"]["auth_token"] = "***configured***" if auth_token else None
        data["api_key_configured"] = bool(api_key)
        data["auth_required"] = bool(auth_token) or not _local_bind(self.home.listen)
        data.pop("config_sources", None)
        return data


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """Рекурсивно объединяет TOML-слои без мутации входных словарей."""
    result = copy.deepcopy(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as stream:
        loaded = tomllib.load(stream)
    if not isinstance(loaded, dict):
        raise ValueError(f"Конфигурация {path} должна быть TOML-таблицей")
    return loaded


def user_config_path() -> Path:
    """Возвращает переносимый путь пользовательской конфигурации."""
    override = os.getenv("BOOSTER_HOME_CONFIG_DIR")
    return (
        Path(override).expanduser() / "home.toml"
        if override
        else Path.home() / ".booster" / "home.toml"
    )


def project_config_path(project: Path | None) -> Path | None:
    if project is None:
        return None
    return project.expanduser().resolve() / ".agents" / "booster" / "home.toml"


def _cli_mapping(overrides: dict[str, Any] | None) -> dict[str, Any]:
    """Преобразует плоские CLI overrides во вложенную структуру config."""
    if not overrides:
        return {}
    result: dict[str, Any] = {}
    sections = {
        "listen": "home",
        "port": "home",
        "verbose": "home",
        "json_logs": "home",
        "auth_token": "home",
        "base_url": "upstream",
        "model": "upstream",
        "api_key": "upstream",
        "context_window": "context",
        "reserve_output": "context",
        "context_policy": "context",
        "workers": "workers",
        "no_persist": None,
        "probe_generation": None,
        "project": None,
    }
    for key, value in overrides.items():
        if value is None or key not in sections:
            continue
        section = sections[key]
        if section is None:
            result[key] = value
        else:
            result.setdefault(section, {})
            target_key = (
                "policy"
                if key == "context_policy"
                else ("max_concurrency" if key == "workers" else key)
            )
            result[section][target_key] = value
    return result


def load_home_config(
    project: str | Path | None = None,
    config_path: str | Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> HomeConfig:
    """Загружает defaults -> user -> project -> explicit -> CLI."""
    project_path = Path(project).expanduser().resolve() if project else None
    merged: dict[str, Any] = {}
    sources: list[str] = []
    for path in (user_config_path(), project_config_path(project_path)):
        if path is not None and path.is_file():
            merged = _deep_merge(merged, _read_toml(path))
            sources.append(str(path))
    if config_path is not None:
        explicit = Path(config_path).expanduser().resolve()
        if not explicit.is_file():
            raise FileNotFoundError(f"Явный Home config не найден: {explicit}")
        merged = _deep_merge(merged, _read_toml(explicit))
        sources.append(str(explicit))
    merged = _deep_merge(merged, _cli_mapping(cli_overrides))
    if project_path is not None:
        merged["project"] = project_path
    merged["config_sources"] = sources
    return HomeConfig.model_validate(merged)
