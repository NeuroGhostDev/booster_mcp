"""Typed contracts for the read-only Booster Observatory API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RepoId = str
ErrorCode = Literal[
    "REPO_NOT_FOUND",
    "SYMBOL_NOT_FOUND",
    "FILE_NOT_FOUND",
    "SNAPSHOT_NOT_FOUND",
    "INDEX_NOT_READY",
    "INVALID_ARGUMENT",
    "RATE_LIMITED",
    "TIMEOUT",
    "INTERNAL_ERROR",
]


class SymbolFocusRequest(BaseModel):
    """Request to resolve a symbol in one allowlisted repository."""

    model_config = ConfigDict(extra="forbid")

    repo_id: RepoId = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
    )
    query: str = Field(min_length=1, max_length=512)

    @field_validator("repo_id", "query")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class SearchRequest(BaseModel):
    """Request for bounded hybrid repository search."""

    model_config = ConfigDict(extra="forbid")

    repo_id: RepoId = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
    )
    query: str = Field(min_length=2, max_length=512)
    limit: int = Field(default=8, ge=1, le=20)

    @field_validator("repo_id", "query")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ImpactRequest(BaseModel):
    """Request for bounded graph impact analysis."""

    model_config = ConfigDict(extra="forbid")

    repo_id: RepoId = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
    )
    target: str = Field(min_length=1, max_length=512)
    max_depth: int = Field(default=3, ge=1, le=4)

    @field_validator("repo_id", "target")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class HistoryRequest(BaseModel):
    """Request for bounded git history and blame context."""

    model_config = ConfigDict(extra="forbid")

    repo_id: RepoId = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
    )
    path: str | None = Field(default=None, min_length=1, max_length=512)
    symbol: str | None = Field(default=None, min_length=1, max_length=512)
    limit: int = Field(default=8, ge=1, le=20)

    @field_validator("repo_id", "path", "symbol")
    @classmethod
    def strip_optional_values(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def require_target(self) -> "HistoryRequest":
        if not self.path and not self.symbol:
            raise ValueError("path or symbol is required")
        return self


class DiagnosticsRequest(BaseModel):
    """Request for safe, read-only diagnostics of repository-relative files."""

    model_config = ConfigDict(extra="forbid")

    repo_id: RepoId = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
    )
    paths: list[str] = Field(min_length=1, max_length=20)

    @field_validator("repo_id")
    @classmethod
    def strip_repo_id(cls, value: str) -> str:
        return value.strip()

    @field_validator("paths")
    @classmethod
    def validate_paths(cls, value: list[str]) -> list[str]:
        paths = [path.strip() for path in value]
        if any(not path for path in paths):
            raise ValueError("paths must not contain blank values")
        return paths


class RelatedTestsRequest(BaseModel):
    """Request for deterministic graph- and path-based related test discovery."""

    model_config = ConfigDict(extra="forbid")

    repo_id: RepoId = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
    )
    target: str = Field(min_length=1, max_length=512)
    limit: int = Field(default=8, ge=1, le=20)

    @field_validator("repo_id", "target")
    @classmethod
    def strip_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class SnapshotCompareRequest(BaseModel):
    """Request to compare two immutable repository snapshots."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    repo_id: RepoId = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
    )
    from_id: str = Field(
        alias="from",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
    )
    to_id: str = Field(
        alias="to",
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
    )

    @field_validator("repo_id", "from_id", "to_id")
    @classmethod
    def strip_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class RepositoryMetadata(BaseModel):
    """Metadata that can be safely shown to a browser client."""

    id: RepoId
    generation_id: str | None = None
    commit: str | None = None


class SymbolLocation(BaseModel):
    """Repository-relative symbol location."""

    name: str
    path: str
    line: int = Field(ge=1)


class FocusSymbolResult(BaseModel):
    symbol: SymbolLocation


class UIFocus(BaseModel):
    path: str


class UIState(BaseModel):
    focus: UIFocus | None = None
    highlights: list[str] | None = None
    mode: str | None = None


class FocusSymbolPayload(BaseModel):
    repo: RepositoryMetadata
    result: FocusSymbolResult
    ui: UIState


class SearchMatch(BaseModel):
    path: str
    symbol: str | None = None
    score: float | None = None
    kind: str | None = None


class SearchResult(BaseModel):
    matches: list[SearchMatch] = Field(default_factory=list)


class SearchPayload(BaseModel):
    repo: RepositoryMetadata
    result: SearchResult
    ui: UIState


class ImpactRisk(BaseModel):
    level: str
    score: float | int


class ImpactConnection(BaseModel):
    source: str
    target: str
    type: str = "CALLS"


class ImpactResult(BaseModel):
    target: str
    target_file: str | None = None
    affected_files: list[str] = Field(default_factory=list)
    callers: list[str] = Field(default_factory=list)
    callees: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    connections: list[ImpactConnection] = Field(default_factory=list)
    depth: int = Field(ge=1)
    risk: ImpactRisk | None = None


class ImpactPayload(BaseModel):
    repo: RepositoryMetadata
    result: ImpactResult
    ui: UIState


class HistoryCommit(BaseModel):
    hash: str
    short_hash: str
    author: str
    date: str
    message: str


class HistoryBlame(BaseModel):
    hash: str
    short_hash: str
    author: str | None = None
    date: str | None = None
    summary: str | None = None
    sample_line: str | None = None


class HistoryResult(BaseModel):
    path: str | None = None
    symbol: str | None = None
    commits: list[HistoryCommit] = Field(default_factory=list)
    blame: list[HistoryBlame] = Field(default_factory=list)
    history_hint: str


class HistoryPayload(BaseModel):
    repo: RepositoryMetadata
    result: HistoryResult
    ui: UIState


class DiagnosticsSummary(BaseModel):
    status: str
    total: int = Field(ge=0)
    by_severity: dict[str, int] = Field(default_factory=dict)


class DiagnosticFinding(BaseModel):
    source: str
    severity: str
    file: str
    line: int | None = None
    column: int | None = None
    message: str
    rule: str | None = None
    status: str | None = None


class DiagnosticsResult(BaseModel):
    paths_checked: list[str] = Field(default_factory=list)
    summary: DiagnosticsSummary
    findings: list[DiagnosticFinding] = Field(default_factory=list)


class DiagnosticsPayload(BaseModel):
    repo: RepositoryMetadata
    result: DiagnosticsResult
    ui: UIState


class RelatedTest(BaseModel):
    path: str
    relation: Literal["direct", "caller", "import", "name"]


class RelatedTestsResult(BaseModel):
    target: str
    tests: list[RelatedTest] = Field(default_factory=list)


class RelatedTestsPayload(BaseModel):
    repo: RepositoryMetadata
    result: RelatedTestsResult
    ui: UIState


class SnapshotReference(BaseModel):
    id: str
    commit: str | None = None
    commit_short: str | None = None
    branch: str | None = None
    captured_at_utc: str | None = None
    dirty: bool | None = None
    indexed_files: int | None = None


class SnapshotConnectionDiff(BaseModel):
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)


class SnapshotCompareResult(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_snapshot: SnapshotReference = Field(alias="from")
    to_snapshot: SnapshotReference = Field(alias="to")
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)
    stable: list[str] = Field(default_factory=list)
    unverified: list[str] = Field(default_factory=list)
    connections: SnapshotConnectionDiff = Field(default_factory=SnapshotConnectionDiff)
    evidence: str = "scan_report.file_manifest"
    summary: dict[str, int] = Field(default_factory=dict)


class SnapshotComparePayload(BaseModel):
    repo: RepositoryMetadata
    result: SnapshotCompareResult
    ui: UIState


class SnapshotListResult(BaseModel):
    snapshots: list[SnapshotReference] = Field(default_factory=list)


class SnapshotListPayload(BaseModel):
    repo: RepositoryMetadata
    result: SnapshotListResult
    ui: UIState


class ArchitectureRequest(BaseModel):
    """Request for a bounded architecture overview."""

    model_config = ConfigDict(extra="forbid")

    repo_id: RepoId = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$",
    )
    focus: str | None = Field(default=None, max_length=256)

    @field_validator("repo_id", "focus")
    @classmethod
    def strip_optional_values(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class ArchitectureResult(BaseModel):
    focus: str | None = None
    map: str
    stats: dict[str, Any] = Field(default_factory=dict)


class ArchitecturePayload(BaseModel):
    repo: RepositoryMetadata
    result: ArchitectureResult
    ui: UIState


class StatusPayload(BaseModel):
    status: str
    mode: str
    webmcp: bool
    repo_id: RepoId | None = None
    generation_id: str | None = None
    commit: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    repo: RepositoryMetadata | None = None


class ApiError(BaseModel):
    code: ErrorCode
    message: str
    retryable: bool = False


class ApiMeta(BaseModel):
    duration_ms: int = Field(ge=0)
    cached: bool = False


class ApiResponse(BaseModel):
    """Common envelope used by browser-facing operation responses."""

    ok: bool
    request_id: str
    repo: RepositoryMetadata | None = None
    result: Any = None
    ui: UIState = Field(default_factory=UIState)
    meta: ApiMeta | None = None
    error: ApiError | None = None
