import { boosterApi } from "/static/api-client.js";
import { createCityAdapter } from "/static/city-adapter.js";
import { createContextualToolManager } from "/static/contextual-tools.js";
import { createWebMCPRegistry } from "/static/webmcp-registry.js";
import { readBoosterUrlState, writeBoosterUrlState } from "/static/url-state.js";
import {
  createFocusSymbolTool,
  createExplainHistoryTool,
  createFindRelatedTestsTool,
  createInspectArchitectureTool,
  createCompareSnapshotsTool,
  createSearchCodeTool,
  createShowDiagnosticsTool,
  createTraceImpactTool,
} from "/static/webmcp-tools.js";
import { workspaceStore } from "/static/workspace-store.js";

const elements = {
  repo: document.getElementById("repo-id"),
  generation: document.getElementById("generation-id"),
  commit: document.getElementById("commit-id"),
  webmcp: document.getElementById("webmcp-status"),
  index: document.getElementById("index-status"),
  city: document.getElementById("city-frame"),
  cityStatus: document.getElementById("city-status"),
  activityTool: document.getElementById("activity-tool"),
  activitySymbol: document.getElementById("activity-symbol"),
  activityGeneration: document.getElementById("activity-generation"),
  activityState: document.getElementById("activity-state"),
  error: document.getElementById("app-error"),
  focusForm: document.getElementById("focus-form"),
  focusInput: document.getElementById("focus-symbol"),
  searchForm: document.getElementById("search-form"),
  searchInput: document.getElementById("search-query"),
  searchResults: document.getElementById("search-results"),
  impactForm: document.getElementById("impact-form"),
  impactInput: document.getElementById("impact-target"),
  impactDepth: document.getElementById("impact-depth"),
  impactTarget: document.getElementById("impact-target-value"),
  impactFiles: document.getElementById("impact-files"),
  impactCallers: document.getElementById("impact-callers"),
  impactCallees: document.getElementById("impact-callees"),
  impactTests: document.getElementById("impact-tests"),
  historyHint: document.getElementById("history-hint"),
  historyCommits: document.getElementById("history-commits"),
  historyBlame: document.getElementById("history-blame"),
  historyList: document.getElementById("history-list"),
  diagnosticsSummary: document.getElementById("diagnostics-summary"),
  diagnosticsList: document.getElementById("diagnostics-list"),
  relatedTestsList: document.getElementById("related-tests-list"),
  historyForm: document.getElementById("history-form"),
  historyInput: document.getElementById("history-target"),
  diagnosticsForm: document.getElementById("diagnostics-form"),
  diagnosticsInput: document.getElementById("diagnostics-paths"),
  relatedTestsForm: document.getElementById("related-tests-form"),
  relatedTestsInput: document.getElementById("related-tests-target"),
  snapshotForm: document.getElementById("snapshot-form"),
  snapshotFrom: document.getElementById("snapshot-from"),
  snapshotTo: document.getElementById("snapshot-to"),
  snapshotList: document.getElementById("snapshot-list"),
  snapshotSummary: document.getElementById("snapshot-summary"),
  snapshotDiff: document.getElementById("snapshot-diff"),
  architectureMap: document.getElementById("architecture-map"),
  shareButton: document.getElementById("share-state"),
  shareStatus: document.getElementById("share-status"),
  contextualStatus: document.getElementById("contextual-status"),
};

const city = createCityAdapter({ frame: elements.city, workspace: workspaceStore });
const registry = createWebMCPRegistry({
  onStatus(status) {
    elements.webmcp.textContent = status.toUpperCase();
    elements.webmcp.dataset.status = status;
  },
});

let loadedCityUrl = null;
let statusPollTimer = null;

function applyStatus(status) {
  const generationChanged = workspaceStore.applyStatus(status);
  if (generationChanged) {
    city.reset?.();
    city.clearHighlights();
    city.clearSelection();
    loadedCityUrl = null;
  }
  elements.repo.textContent = status.repo_id || "-";
  elements.generation.textContent = status.generation_id || "-";
  elements.commit.textContent = status.commit || "-";
  elements.index.textContent = String(status.status || "unknown").toUpperCase();

  if (!status.repo_id) {
    elements.cityStatus.textContent = "No repository is configured";
    return;
  }
  if (status.status !== "ready") {
    elements.cityStatus.textContent = `Index ${String(status.status || "not ready")}; waiting`;
    return;
  }
  const cityUrl = `/api/v1/city/html?repo_id=${encodeURIComponent(status.repo_id)}`;
  if (loadedCityUrl !== cityUrl) {
    loadedCityUrl = cityUrl;
    elements.city.src = cityUrl;
  }
}

function scheduleStatusPoll(repoId, delayMs) {
  if (statusPollTimer) window.clearTimeout(statusPollTimer);
  statusPollTimer = window.setTimeout(async () => {
    try {
      const nextStatus = await boosterApi.status(repoId);
      applyStatus(nextStatus);
      scheduleStatusPoll(repoId, nextStatus.status === "ready" ? 5000 : 1000);
    } catch (_error) {
      scheduleStatusPoll(repoId, 5000);
    }
  }, delayMs);
}

window.addEventListener("booster:generation-mismatch", () => {
  const repoId = workspaceStore.getState().repoId;
  if (repoId) scheduleStatusPoll(repoId, 0);
});

function showError(error) {
  elements.error.textContent = error ? String(error.message || error) : "";
  workspaceStore.setError(error ? String(error.message || error) : null);
}

function renderState(state) {
  const action = state.lastAgentAction;
  elements.activityTool.textContent = action?.tool || "No agent action";
  elements.activitySymbol.textContent = action?.symbol || state.selectedFile || "-";
  elements.activityGeneration.textContent =
    action?.generation_id || action?.generationId || state.generationId || "-";
  elements.activityState.textContent = action?.status || "idle";
  elements.activityState.dataset.status = action?.status || "idle";
  if (state.error) elements.error.textContent = state.error;
  renderSearchResults(state.searchResults || []);
  renderImpact(state.impact);
  renderHistory(state.history);
  renderDiagnostics(state.diagnostics);
  renderRelatedTests(state.relatedTests);
  renderSnapshots(state);
  renderArchitecture(state.architecture);
  writeBoosterUrlState(state);
}

function renderSearchResults(matches) {
  if (!elements.searchResults) return;
  elements.searchResults.replaceChildren();
  matches.forEach((match) => {
    const item = document.createElement("li");
    item.textContent = match.symbol ? `${match.symbol} | ${match.path}` : match.path;
    elements.searchResults.appendChild(item);
  });
}

function renderImpact(impact) {
  if (!elements.impactTarget) return;
  elements.impactTarget.textContent = impact?.target || "-";
  elements.impactFiles.textContent = String(impact?.affected_files?.length || 0);
  elements.impactCallers.textContent = String(impact?.callers?.length || 0);
  elements.impactCallees.textContent = String(impact?.callees?.length || 0);
  elements.impactTests.textContent = String(impact?.tests?.length || 0);
}

function renderHistory(history) {
  if (!elements.historyHint) return;
  elements.historyHint.textContent = history?.history_hint || "-";
  elements.historyCommits.textContent = String(history?.commits?.length || 0);
  elements.historyBlame.textContent = String(history?.blame?.length || 0);
  elements.historyList.replaceChildren();
  (history?.commits || []).slice(0, 8).forEach((commit) => {
    const item = document.createElement("li");
    item.textContent = `${commit.short_hash} | ${commit.message}`;
    elements.historyList.appendChild(item);
  });
  (history?.blame || []).slice(0, 8).forEach((entry) => {
    const item = document.createElement("li");
    item.textContent = `blame ${entry.short_hash} | ${entry.summary || entry.sample_line || "entry"}`;
    elements.historyList.appendChild(item);
  });
}

function renderDiagnostics(diagnostics) {
  if (!elements.diagnosticsSummary) return;
  const summary = diagnostics?.summary;
  elements.diagnosticsSummary.textContent = summary
    ? `${summary.status}: ${summary.total} findings`
    : "No diagnostics loaded";
  elements.diagnosticsList.replaceChildren();
  (diagnostics?.findings || []).forEach((finding) => {
    const item = document.createElement("li");
    item.textContent = `${finding.severity} | ${finding.file}:${finding.line || 0} | ${finding.message}`;
    elements.diagnosticsList.appendChild(item);
  });
}

function renderRelatedTests(relatedTests) {
  if (!elements.relatedTestsList) return;
  elements.relatedTestsList.replaceChildren();
  (relatedTests?.tests || []).forEach((test) => {
    const item = document.createElement("li");
    item.textContent = `${test.relation} | ${test.path}`;
    elements.relatedTestsList.appendChild(item);
  });
}

function renderSnapshots(state) {
  if (!elements.snapshotList) return;
  const snapshots = state.snapshots || [];
  elements.snapshotList.replaceChildren();
  snapshots.slice(0, 20).forEach((snapshot) => {
    const item = document.createElement("li");
    item.textContent = `${snapshot.id} | ${snapshot.commit_short || "no commit"}`;
    elements.snapshotList.appendChild(item);
  });
  if (snapshots.length && !elements.snapshotFrom.value) {
    elements.snapshotFrom.value = snapshots[Math.min(1, snapshots.length - 1)].id;
  }
  if (snapshots.length && !elements.snapshotTo.value) {
    elements.snapshotTo.value = snapshots[0].id;
  }
  const comparison = state.snapshotComparison;
  elements.snapshotSummary.textContent = comparison
    ? `added ${comparison.added.length} | removed ${comparison.removed.length} | changed ${comparison.changed.length} | stable ${comparison.stable.length} | unverified ${comparison.unverified?.length || 0}`
    : "No snapshot comparison loaded";
  elements.snapshotDiff.replaceChildren();
  if (!comparison) return;
  [
    ["added", comparison.added],
    ["removed", comparison.removed],
    ["changed", comparison.changed],
    ["unverified", comparison.unverified || []],
  ].forEach(([label, paths]) => {
    paths.slice(0, 20).forEach((path) => {
      const item = document.createElement("li");
      item.textContent = `${label} | ${path}`;
      elements.snapshotDiff.appendChild(item);
    });
  });
}

function renderArchitecture(architecture) {
  if (!elements.architectureMap) return;
  elements.architectureMap.textContent = architecture?.map || "No architecture overview loaded";
}

async function focusFromHuman(symbol) {
  const repoId = workspaceStore.getState().repoId;
  if (!repoId) return;
  workspaceStore.agentActionStarted("booster_focus_symbol", symbol);
  try {
    const response = await boosterApi.focusSymbol(repoId, symbol);
    workspaceStore.applyFocusResult(response);
    city.focusFile(response.result.symbol.path);
    workspaceStore.agentActionSucceeded("booster_focus_symbol", { symbol });
  } catch (error) {
    workspaceStore.agentActionFailed("booster_focus_symbol", error, symbol);
    showError(error);
  }
}

async function searchFromHuman(query) {
  const repoId = workspaceStore.getState().repoId;
  if (!repoId) return;
  workspaceStore.agentActionStarted("booster_search_code", query);
  try {
    const response = await boosterApi.searchCode(repoId, query, 8);
    workspaceStore.applySearchResult(response);
    city.clearHighlights();
    city.highlightFiles(response.result.matches.map((match) => match.path));
    workspaceStore.agentActionSucceeded("booster_search_code", { symbol: query });
  } catch (error) {
    workspaceStore.agentActionFailed("booster_search_code", error, query);
    showError(error);
  }
}

async function impactFromHuman(target, maxDepth) {
  const repoId = workspaceStore.getState().repoId;
  if (!repoId) return;
  workspaceStore.agentActionStarted("booster_trace_impact", target);
  try {
    const response = await boosterApi.traceImpact(repoId, target, maxDepth);
    workspaceStore.applyImpactResult(response);
    city.showImpact(response.result);
    workspaceStore.agentActionSucceeded("booster_trace_impact", { symbol: target });
  } catch (error) {
    workspaceStore.agentActionFailed("booster_trace_impact", error, target);
    showError(error);
  }
}

async function historyFromHuman(target) {
  const repoId = workspaceStore.getState().repoId;
  if (!repoId) return;
  workspaceStore.agentActionStarted("booster_explain_history", target);
  try {
    const response = await boosterApi.explainHistory(repoId, { path: target, limit: 8 });
    workspaceStore.applyHistoryResult(response);
    city.showHistory(response.result);
    workspaceStore.agentActionSucceeded("booster_explain_history", { symbol: target });
  } catch (error) {
    workspaceStore.agentActionFailed("booster_explain_history", error, target);
    showError(error);
  }
}

async function diagnosticsFromHuman(paths) {
  const repoId = workspaceStore.getState().repoId;
  if (!repoId) return;
  const target = paths.join(", ");
  workspaceStore.agentActionStarted("booster_show_diagnostics", target);
  try {
    const response = await boosterApi.showDiagnostics(repoId, paths);
    workspaceStore.applyDiagnosticsResult(response);
    city.showDiagnostics(response.result);
    workspaceStore.agentActionSucceeded("booster_show_diagnostics", { symbol: target });
  } catch (error) {
    workspaceStore.agentActionFailed("booster_show_diagnostics", error, target);
    showError(error);
  }
}

async function relatedTestsFromHuman(target) {
  const repoId = workspaceStore.getState().repoId;
  if (!repoId) return;
  workspaceStore.agentActionStarted("booster_find_related_tests", target);
  try {
    const response = await boosterApi.findRelatedTests(repoId, target, 8);
    workspaceStore.applyRelatedTestsResult(response);
    city.showRelatedTests(
      response.result.tests.map((item) => item.path),
      workspaceStore.getState().selectedFile,
    );
    workspaceStore.agentActionSucceeded("booster_find_related_tests", { symbol: target });
  } catch (error) {
    workspaceStore.agentActionFailed("booster_find_related_tests", error, target);
    showError(error);
  }
}

async function compareSnapshotsFromHuman(fromId, toId) {
  const repoId = workspaceStore.getState().repoId;
  if (!repoId) return;
  const target = `${fromId} -> ${toId}`;
  workspaceStore.agentActionStarted("booster_compare_snapshots", target);
  try {
    const response = await boosterApi.compareSnapshots(repoId, fromId, toId);
    workspaceStore.applySnapshotComparison(response);
    city.showSnapshotComparison(response.result);
    workspaceStore.agentActionSucceeded("booster_compare_snapshots", { symbol: target });
  } catch (error) {
    workspaceStore.agentActionFailed("booster_compare_snapshots", error, target);
    showError(error);
  }
}

async function start() {
  const sharedState = readBoosterUrlState();

  let status;
  try {
    status = await boosterApi.status();
  } catch (error) {
    showError(error);
    registry.stop();
    return;
  }

  elements.city.addEventListener("load", () => {
    elements.cityStatus.textContent = "Code City loaded";
  });
  elements.city.addEventListener("error", () => {
    elements.cityStatus.textContent = "Code City unavailable";
  });
  applyStatus(status);
  if (sharedState.repoId && sharedState.repoId !== status.repo_id) {
    showError(new Error("Shared URL repository does not match the current repository"));
  }
  if (sharedState.selectedFile && sharedState.repoId === status.repo_id) {
    workspaceStore.selectFile(sharedState.selectedFile, null, "url");
    city.focusFile(sharedState.selectedFile);
  }
  workspaceStore.subscribe(renderState);
  renderState(workspaceStore.getState());
  try {
    workspaceStore.applySnapshotList(await boosterApi.listSnapshots(status.repo_id));
  } catch (_error) {
    // Snapshot history is optional; the rest of the workspace remains usable.
  }

  const tool = createFocusSymbolTool({
    api: boosterApi,
    workspace: workspaceStore,
    city,
    registry,
    repoId: () => workspaceStore.getState().repoId,
  });
  const searchTool = createSearchCodeTool({
    api: boosterApi,
    workspace: workspaceStore,
    city,
    registry,
    repoId: () => workspaceStore.getState().repoId,
  });
  const impactTool = createTraceImpactTool({
    api: boosterApi,
    workspace: workspaceStore,
    city,
    registry,
    repoId: () => workspaceStore.getState().repoId,
  });
  const historyTool = createExplainHistoryTool({
    api: boosterApi,
    workspace: workspaceStore,
    city,
    registry,
    repoId: () => workspaceStore.getState().repoId,
  });
  const diagnosticsTool = createShowDiagnosticsTool({
    api: boosterApi,
    workspace: workspaceStore,
    city,
    registry,
    repoId: () => workspaceStore.getState().repoId,
  });
  const relatedTestsTool = createFindRelatedTestsTool({
    api: boosterApi,
    workspace: workspaceStore,
    city,
    registry,
    repoId: () => workspaceStore.getState().repoId,
  });
  const compareSnapshotsTool = createCompareSnapshotsTool({
    api: boosterApi,
    workspace: workspaceStore,
    city,
    registry,
    repoId: () => workspaceStore.getState().repoId,
  });
  const inspectArchitectureTool = createInspectArchitectureTool({
    api: boosterApi,
    workspace: workspaceStore,
    city,
    registry,
    repoId: () => workspaceStore.getState().repoId,
  });
  const contextual = createContextualToolManager({
    api: boosterApi,
    workspace: workspaceStore,
    city,
    registry,
    onStatus(status) {
      if (elements.contextualStatus) elements.contextualStatus.textContent = status.toUpperCase();
    },
  });
  const tools = [
    tool,
    searchTool,
    impactTool,
    historyTool,
    diagnosticsTool,
    relatedTestsTool,
    compareSnapshotsTool,
    inspectArchitectureTool,
  ];
  window.BoosterObservatory = { workspace: workspaceStore, city, registry, contextual, tools };
  contextual.start();
  try {
    await registry.registerTools(tools);
  } catch (error) {
    showError(error);
  }

  if (status.repo_id && status.mode !== "demo") {
    scheduleStatusPoll(status.repo_id, status.status === "ready" ? 5000 : 1000);
  }
  if (
    sharedState.mode === "snapshots" &&
    sharedState.fromSnapshot &&
    sharedState.toSnapshot &&
    status.repo_id
  ) {
    compareSnapshotsFromHuman(sharedState.fromSnapshot, sharedState.toSnapshot);
  }
}

elements.focusForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const symbol = elements.focusInput.value.trim();
  if (symbol) focusFromHuman(symbol);
});

elements.searchForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  const query = elements.searchInput.value.trim();
  if (query.length >= 2) searchFromHuman(query);
});

elements.impactForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  const target = elements.impactInput.value.trim();
  const maxDepth = Number(elements.impactDepth.value || 3);
  if (target) impactFromHuman(target, maxDepth);
});

elements.historyForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  const target = elements.historyInput.value.trim();
  if (target) historyFromHuman(target);
});

elements.diagnosticsForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  const paths = elements.diagnosticsInput.value
    .split(",")
    .map((path) => path.trim())
    .filter(Boolean);
  if (paths.length) diagnosticsFromHuman(paths);
});

elements.relatedTestsForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  const target = elements.relatedTestsInput.value.trim();
  if (target) relatedTestsFromHuman(target);
});

elements.snapshotForm?.addEventListener("submit", (event) => {
  event.preventDefault();
  const fromId = elements.snapshotFrom.value.trim();
  const toId = elements.snapshotTo.value.trim();
  if (fromId && toId) compareSnapshotsFromHuman(fromId, toId);
});

elements.shareButton?.addEventListener("click", async () => {
  const url = writeBoosterUrlState(workspaceStore.getState(), { replace: false });
  try {
    await navigator.clipboard.writeText(url);
    elements.shareStatus.textContent = "Share URL copied";
  } catch (_error) {
    elements.shareStatus.textContent = url;
  }
});

start();
