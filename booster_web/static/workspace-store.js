/** @typedef {{name: string, path: string, line?: number}|null} SelectedSymbol */
/** @typedef {{tool: string, symbol?: string, status: string, generationId?: string, generation_id?: string, durationMs?: number, error?: string}} AgentAction */

const SELECTION_EVENT = "booster:selection-changed";
const AGENT_EVENT = "booster:agent-action";
const GENERATION_MISMATCH_EVENT = "booster:generation-mismatch";

function createWorkspaceStore(initial = {}) {
  let state = {
    repoId: initial.repoId ?? null,
    generationId: initial.generationId ?? null,
    selectedFile: initial.selectedFile ?? null,
    selectedSymbol: initial.selectedSymbol ?? null,
    searchResults: initial.searchResults ?? [],
    highlightedFiles: initial.highlightedFiles ?? [],
    highlightedEdges: initial.highlightedEdges ?? [],
    activeMode: initial.activeMode ?? "default",
    impact: initial.impact ?? null,
    history: initial.history ?? null,
    diagnostics: initial.diagnostics ?? null,
    relatedTests: initial.relatedTests ?? null,
    snapshots: initial.snapshots ?? [],
    snapshotComparison: initial.snapshotComparison ?? null,
    architecture: initial.architecture ?? null,
    lastAgentAction: initial.lastAgentAction ?? null,
    error: initial.error ?? null,
  };
  const listeners = new Set();

  function ensureCurrentResponse(response) {
    const responseGeneration = response?.repo?.generation_id;
    const responseRepo = response?.repo?.id;
    const generationMatches =
      !responseGeneration || !state.generationId || responseGeneration === state.generationId;
    const repositoryMatches = !responseRepo || !state.repoId || responseRepo === state.repoId;
    if (generationMatches && repositoryMatches) return;

    const detail = {
      responseGeneration: responseGeneration || null,
      currentGeneration: state.generationId,
      responseRepo: responseRepo || null,
      currentRepo: state.repoId,
    };
    if (typeof window !== "undefined" && typeof window.dispatchEvent === "function") {
      window.dispatchEvent(new CustomEvent(GENERATION_MISMATCH_EVENT, { detail }));
    }
    const error = new Error("Repository response belongs to a stale workspace generation");
    error.code = "STALE_GENERATION";
    throw error;
  }

  function snapshot() {
    return { ...state };
  }

  function emit(eventName, detail) {
    const value = snapshot();
    listeners.forEach((listener) => listener(value, eventName));
    if (typeof window !== "undefined" && typeof window.dispatchEvent === "function") {
      window.dispatchEvent(new CustomEvent(eventName, { detail }));
    }
  }

  function update(patch, eventName = null, detail = patch) {
    state = { ...state, ...patch };
    if (eventName) emit(eventName, detail);
    else listeners.forEach((listener) => listener(snapshot(), null));
    return snapshot();
  }

  const store = {
    getState: snapshot,
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    setRepo(repoId) {
      return update({ repoId: repoId || null });
    },
    applyStatus(status) {
      const nextRepoId = status?.repo_id || null;
      const generationId = status?.generation_id || state.generationId;
      const repositoryChanged = Boolean(state.repoId && nextRepoId && state.repoId !== nextRepoId);
      const generationChanged = Boolean(
        state.generationId && generationId && state.generationId !== generationId,
      );
      const patch = {
        repoId: nextRepoId,
        generationId: generationId || null,
      };
      if (repositoryChanged || generationChanged) {
        Object.assign(patch, {
          selectedFile: null,
          selectedSymbol: null,
          searchResults: [],
          highlightedFiles: [],
          highlightedEdges: [],
          activeMode: "default",
          impact: null,
          history: null,
          diagnostics: null,
          relatedTests: null,
          snapshotComparison: null,
          architecture: null,
          lastAgentAction: null,
          error: null,
        });
      }
      update(
        patch,
        repositoryChanged || generationChanged ? "booster:generation-changed" : null,
        { repositoryChanged, generationChanged, generationId },
      );
      return repositoryChanged || generationChanged;
    },
    selectFile(file, symbol = null, source = "human") {
      const selectedFile = file || null;
      const selectedSymbol = symbol || null;
      return update(
        { selectedFile, selectedSymbol, error: null },
        SELECTION_EVENT,
        { file: selectedFile, symbol: selectedSymbol, source },
      );
    },
    clearSelection() {
      return update(
        { selectedFile: null, selectedSymbol: null },
        SELECTION_EVENT,
        { file: null, symbol: null, source: "application" },
      );
    },
    setError(error) {
      return update({ error: error ? String(error) : null });
    },
    applyFocusResult(response) {
      ensureCurrentResponse(response);
      const symbol = response?.result?.symbol || null;
      const repoId = response?.repo?.id || state.repoId;
      if (!symbol?.path) return update({ repoId, error: "Focus response did not contain a file" });
      return update(
        {
          repoId,
          generationId: response?.repo?.generation_id || state.generationId,
          selectedFile: symbol.path,
          selectedSymbol: symbol,
          error: null,
        },
        SELECTION_EVENT,
        { file: symbol.path, symbol, source: "agent" },
      );
    },
    applySearchResult(response) {
      ensureCurrentResponse(response);
      const matches = response?.result?.matches || [];
      const files = response?.ui?.highlights || matches.map((match) => match.path);
      return update(
        {
          repoId: response?.repo?.id || state.repoId,
          generationId: response?.repo?.generation_id || state.generationId,
          searchResults: matches,
          highlightedFiles: files,
          highlightedEdges: [],
          activeMode: "search",
          impact: null,
          history: null,
          diagnostics: null,
          relatedTests: null,
          snapshotComparison: null,
          architecture: null,
          error: null,
        },
        "booster:highlights-changed",
        { files, source: "agent" },
      );
    },
    applyImpactResult(response) {
      ensureCurrentResponse(response);
      const result = response?.result || null;
      const files = response?.ui?.highlights || result?.affected_files || [];
      const targetFile = result?.target_file || response?.ui?.focus?.path || null;
      const next = update(
        {
          repoId: response?.repo?.id || state.repoId,
          generationId: response?.repo?.generation_id || state.generationId,
          selectedFile: targetFile || state.selectedFile,
          selectedSymbol: targetFile ? { name: result?.target || "", path: targetFile } : state.selectedSymbol,
          searchResults: [],
          highlightedFiles: files,
          highlightedEdges: [],
          activeMode: "impact",
          impact: result,
          history: null,
          diagnostics: null,
          relatedTests: null,
          snapshotComparison: null,
          architecture: null,
          error: null,
        },
        "booster:impact-loaded",
        { impact: result, source: "agent" },
      );
      if (targetFile) {
        emit("booster:selection-changed", {
          file: targetFile,
          symbol: next.selectedSymbol,
          source: "agent",
        });
      }
      emit("booster:highlights-changed", { files, source: "agent" });
      return next;
    },
    applyHistoryResult(response) {
      ensureCurrentResponse(response);
      const result = response?.result || null;
      const path = result?.path || response?.ui?.focus?.path || null;
      const files = path ? [path] : [];
      const symbol = result?.symbol && path ? { name: result.symbol, path } : null;
      const next = update(
        {
          repoId: response?.repo?.id || state.repoId,
          generationId: response?.repo?.generation_id || state.generationId,
          selectedFile: path || state.selectedFile,
          selectedSymbol: symbol || state.selectedSymbol,
          searchResults: [],
          highlightedFiles: files,
          highlightedEdges: [],
          activeMode: "history",
          impact: null,
          history: result,
          diagnostics: null,
          relatedTests: null,
          snapshotComparison: null,
          architecture: null,
          error: null,
        },
        "booster:history-loaded",
        { history: result, source: "agent" },
      );
      if (path) {
        emit("booster:selection-changed", {
          file: path,
          symbol: next.selectedSymbol,
          source: "agent",
        });
      }
      emit("booster:highlights-changed", { files, source: "agent" });
      return next;
    },
    applyDiagnosticsResult(response) {
      ensureCurrentResponse(response);
      const result = response?.result || null;
      const findings = Array.isArray(result?.findings) ? result.findings : [];
      const files = response?.ui?.highlights || [
        ...new Set(findings.map((finding) => finding.file).filter(Boolean)),
      ];
      const next = update(
        {
          repoId: response?.repo?.id || state.repoId,
          generationId: response?.repo?.generation_id || state.generationId,
          searchResults: [],
          highlightedFiles: files,
          highlightedEdges: [],
          activeMode: "diagnostics",
          impact: null,
          history: null,
          diagnostics: result,
          relatedTests: null,
          snapshotComparison: null,
          error: null,
        },
        "booster:diagnostics-loaded",
        { diagnostics: result, source: "agent" },
      );
      emit("booster:highlights-changed", { files, source: "agent" });
      return next;
    },
    applyRelatedTestsResult(response) {
      ensureCurrentResponse(response);
      const result = response?.result || null;
      const tests = Array.isArray(result?.tests) ? result.tests : [];
      const files = response?.ui?.highlights || tests.map((test) => test.path).filter(Boolean);
      const next = update(
        {
          repoId: response?.repo?.id || state.repoId,
          generationId: response?.repo?.generation_id || state.generationId,
          searchResults: [],
          highlightedFiles: files,
          highlightedEdges: [],
          activeMode: "tests",
          impact: null,
          history: null,
          diagnostics: null,
          relatedTests: result,
          snapshotComparison: null,
          architecture: null,
          error: null,
        },
        "booster:related-tests-loaded",
        { relatedTests: result, source: "agent" },
      );
      emit("booster:highlights-changed", { files, source: "agent" });
      return next;
    },
    applySnapshotList(response) {
      ensureCurrentResponse(response);
      return update({
        repoId: response?.repo?.id || state.repoId,
        generationId: response?.repo?.generation_id || state.generationId,
        snapshots: response?.result?.snapshots || [],
        error: null,
      });
    },
    applySnapshotComparison(response) {
      ensureCurrentResponse(response);
      const result = response?.result || null;
      const files = response?.ui?.highlights || [
        ...(result?.added || []),
        ...(result?.changed || []),
      ];
      const next = update(
        {
          repoId: response?.repo?.id || state.repoId,
          generationId: response?.repo?.generation_id || state.generationId,
          searchResults: [],
          highlightedFiles: files,
          highlightedEdges: [],
          activeMode: "snapshots",
          impact: null,
          history: null,
          diagnostics: null,
          relatedTests: null,
          snapshotComparison: result,
          error: null,
        },
        "booster:snapshot-compared",
        { comparison: result, source: "agent" },
      );
      emit("booster:highlights-changed", { files, source: "agent" });
      return next;
    },
    applyArchitectureResult(response) {
      ensureCurrentResponse(response);
      return update(
        {
          repoId: response?.repo?.id || state.repoId,
          generationId: response?.repo?.generation_id || state.generationId,
          searchResults: [],
          highlightedFiles: [],
          highlightedEdges: [],
          impact: null,
          history: null,
          diagnostics: null,
          relatedTests: null,
          snapshotComparison: null,
          architecture: response?.result || null,
          activeMode: "architecture",
          error: null,
        },
        "booster:architecture-loaded",
        { architecture: response?.result || null, source: "agent" },
      );
    },
    clearHighlights() {
      return update(
        {
          highlightedFiles: [],
          highlightedEdges: [],
          searchResults: [],
          impact: null,
          history: null,
          diagnostics: null,
          relatedTests: null,
          snapshotComparison: null,
          architecture: null,
          activeMode: "default",
        },
        "booster:highlights-changed",
        { files: [], source: "application" },
      );
    },
    agentActionStarted(tool, symbol) {
      const action = {
        tool,
        symbol,
        generationId: state.generationId,
        generation_id: state.generationId,
        status: "running",
      };
      return update({ lastAgentAction: action, error: null }, AGENT_EVENT, action);
    },
    agentActionSucceeded(tool, details = {}) {
      const generationId =
        details.generation_id ??
        details.generationId ??
        state.lastAgentAction?.generation_id ??
        state.lastAgentAction?.generationId ??
        state.generationId;
      const action = {
        tool,
        generationId,
        generation_id: generationId,
        ...details,
        status: "completed",
      };
      return update({ lastAgentAction: action, error: null }, AGENT_EVENT, action);
    },
    agentActionFailed(tool, error, symbol = null) {
      const message = error?.message || String(error || "Request failed");
      const action = {
        tool,
        symbol: symbol || state.lastAgentAction?.symbol || null,
        generationId: state.lastAgentAction?.generationId ?? state.generationId,
        generation_id:
          state.lastAgentAction?.generation_id ??
          state.lastAgentAction?.generationId ??
          state.generationId,
        status: "failed",
        error: message,
      };
      return update({ lastAgentAction: action, error: message }, AGENT_EVENT, action);
    },
  };

  return store;
}

const workspaceStore = createWorkspaceStore();
if (typeof window !== "undefined") {
  window.BoosterWorkspaceStore = workspaceStore;
  window.createBoosterWorkspaceStore = createWorkspaceStore;
}

export { createWorkspaceStore, workspaceStore };
