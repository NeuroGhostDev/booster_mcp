import assert from "node:assert/strict";
import test from "node:test";

const listeners = new Map();
globalThis.CustomEvent = class CustomEvent {
  constructor(type, init = {}) {
    this.type = type;
    this.detail = init.detail;
  }
};
globalThis.window = {
  location: { origin: "http://localhost", href: "http://localhost/" },
  history: { replaceState: (_state, _title, path) => { window.__historyPath = path; } },
  addEventListener(type, listener) {
    listeners.set(type, listener);
  },
  removeEventListener(type, listener) {
    if (listeners.get(type) === listener) listeners.delete(type);
  },
  dispatchEvent() {},
};
globalThis.document = {};

const { createWorkspaceStore } = await import("../../../booster_web/static/workspace-store.js");
const { readBoosterUrlState, writeBoosterUrlState } = await import("../../../booster_web/static/url-state.js");
const { createWebMCPRegistry } = await import("../../../booster_web/static/webmcp-registry.js");
const { createContextualToolManager } = await import(
  "../../../booster_web/static/contextual-tools.js"
);
const {
  createCompareSnapshotsTool,
  createFocusSymbolTool,
  createExplainHistoryTool,
  createFindRelatedTestsTool,
  createInspectArchitectureTool,
  createSearchCodeTool,
  createShowDiagnosticsTool,
  createTraceImpactTool,
} = await import("../../../booster_web/static/webmcp-tools.js");
const { createCityAdapter } = await import("../../../booster_web/static/city-adapter.js");

test("shareable URL state contains only safe workspace identifiers", () => {
  window.location.href = "http://localhost/?repo_id=demo&file=src/service.py&mode=impact&from=old&to=new";
  const shared = readBoosterUrlState();
  assert.equal(shared.repoId, "demo");
  assert.equal(shared.selectedFile, "src/service.py");
  assert.equal(shared.mode, "impact");
  assert.equal(shared.fromSnapshot, "old");
  const result = writeBoosterUrlState({
    repoId: "demo",
    selectedFile: "src/service.py",
    activeMode: "snapshots",
    snapshotComparison: { from: { id: "old" }, to: { id: "new" } },
  });
  assert.match(result, /repo_id=demo/);
  assert.match(result, /file=src%2Fservice.py/);
  assert.equal(window.__historyPath, "/?repo_id=demo&file=src%2Fservice.py&mode=snapshots&from=old&to=new");
});

test("WebMCP absence leaves registry usable", async () => {
  document.modelContext = undefined;
  const statuses = [];
  const registry = createWebMCPRegistry({ onStatus: (status) => statuses.push(status) });

  assert.deepEqual(await registry.registerTools([]), []);
  assert.deepEqual(statuses, ["unavailable"]);
});

test("native tool registration and focus execution share workspace state", async () => {
  const registered = [];
  document.modelContext = {
    async registerTool(tool, options) {
      registered.push({ tool, options });
    },
  };
  const workspace = createWorkspaceStore({ repoId: "demo" });
  const cityCalls = [];
  const city = { focusFile: (path) => cityCalls.push(path) };
  const registry = createWebMCPRegistry();
  const tool = createFocusSymbolTool({
    api: {
      async focusSymbol() {
        return {
          repo: { id: "demo" },
          result: { symbol: { name: "full_index", path: "indexer.py", line: 123 } },
        };
      },
    },
    workspace,
    city,
    registry,
    repoId: () => workspace.getState().repoId,
  });

  await registry.registerTools([tool]);
  const result = await tool.execute({ symbol: "RepoIndexer.full_index" });

  assert.equal(registered[0].tool.name, "booster_focus_symbol");
  assert.deepEqual(registered[0].tool.inputSchema.required, ["symbol"]);
  assert.equal(registered[0].tool.inputSchema.additionalProperties, false);
  assert.equal(registered[0].tool.annotations.readOnlyHint, true);
  assert.equal(registered[0].options.signal.aborted, false);
  assert.equal(workspace.getState().selectedFile, "indexer.py");
  assert.equal(workspace.getState().selectedSymbol.line, 123);
  assert.deepEqual(cityCalls, ["indexer.py"]);
  assert.match(result.content[0].text, /indexer\.py:123/);
  registry.stop();
  assert.equal(registered[0].options.signal.aborted, true);
});

test("agent activity trace records the current generation", async () => {
  document.modelContext = { async registerTool() {} };
  const logs = [];
  const workspace = createWorkspaceStore({ repoId: "demo" });
  workspace.applyStatus({ repo_id: "demo", generation_id: "generation-one" });
  const registry = createWebMCPRegistry({ logger: { info: (_label, payload) => logs.push(payload) } });
  const tool = createFocusSymbolTool({
    api: {
      async focusSymbol() {
        return {
          repo: { id: "demo", generation_id: "generation-one" },
          result: { symbol: { name: "target", path: "service.py", line: 1 } },
        };
      },
    },
    workspace,
    city: { focusFile: () => true },
    registry,
    repoId: "demo",
  });

  await tool.execute({ symbol: "target" });

  assert.equal(workspace.getState().lastAgentAction.generation_id, "generation-one");
  assert.equal(logs.find((entry) => entry.event === "call").generation_id, "generation-one");
});

test("API failure leaves the previous selection intact and records failure", async () => {
  const workspace = createWorkspaceStore({ repoId: "demo", selectedFile: "safe.py" });
  const registry = createWebMCPRegistry();
  const tool = createFocusSymbolTool({
    api: { focusSymbol: async () => { throw new Error("symbol not found"); } },
    workspace,
    city: { focusFile: () => { throw new Error("must not be called"); } },
    registry,
    repoId: "demo",
  });

  await assert.rejects(tool.execute({ symbol: "missing" }), /symbol not found/);
  assert.equal(workspace.getState().selectedFile, "safe.py");
  assert.equal(workspace.getState().lastAgentAction.status, "failed");
  assert.equal(workspace.getState().lastAgentAction.symbol, "missing");
});

test("stale asynchronous responses cannot mutate the current workspace", async () => {
  const workspace = createWorkspaceStore({ repoId: "demo" });
  workspace.applyStatus({ repo_id: "demo", generation_id: "generation-one" });
  const cityCalls = [];
  let resolveSearch;
  const search = createSearchCodeTool({
    api: {
      searchCode: () => new Promise((resolve) => { resolveSearch = resolve; }),
    },
    workspace,
    city: { clearHighlights: () => cityCalls.push("clear"), highlightFiles: () => cityCalls.push("highlight") },
    registry: createWebMCPRegistry(),
    repoId: "demo",
  });

  const pending = search.execute({ query: "target" });
  workspace.applyStatus({ repo_id: "demo", generation_id: "generation-two" });
  resolveSearch({
    repo: { id: "demo", generation_id: "generation-one" },
    result: { matches: [{ path: "old.py" }] },
    ui: { highlights: ["old.py"], mode: "search" },
  });

  await assert.rejects(pending, /stale workspace generation/);
  assert.deepEqual(workspace.getState().searchResults, []);
  assert.deepEqual(workspace.getState().highlightedFiles, []);
  assert.deepEqual(cityCalls, []);
});

test("search and impact tools update highlights and impact state", async () => {
  const workspace = createWorkspaceStore({ repoId: "demo" });
  const cityCalls = [];
  const city = {
    clearHighlights: () => cityCalls.push("clear"),
    highlightFiles: (paths) => cityCalls.push(["highlight", paths]),
    showImpact: (result) => cityCalls.push(["impact", result.target]),
  };
  const registry = createWebMCPRegistry();
  const search = createSearchCodeTool({
    api: {
      async searchCode() {
        return {
          repo: { id: "demo" },
          result: { matches: [{ path: "indexer.py", symbol: "target", score: 0.8 }] },
          ui: { highlights: ["indexer.py"], mode: "search" },
        };
      },
    },
    workspace,
    city,
    registry,
    repoId: "demo",
  });
  const impact = createTraceImpactTool({
    api: {
      async traceImpact() {
        return {
          repo: { id: "demo" },
          result: {
            target: "target",
            target_file: "indexer.py",
            affected_files: ["indexer.py", "server.py"],
            callers: ["caller"],
            callees: ["callee"],
            tests: ["tests/test_indexer.py"],
          },
        };
      },
    },
    workspace,
    city,
    registry,
    repoId: "demo",
  });

  await search.execute({ query: "target" });
  assert.deepEqual(workspace.getState().highlightedFiles, ["indexer.py"]);
  assert.equal(workspace.getState().activeMode, "search");
  await impact.execute({ target: "target", max_depth: 3 });
  assert.deepEqual(workspace.getState().highlightedFiles, ["indexer.py", "server.py"]);
  assert.equal(workspace.getState().impact.target, "target");
  assert.deepEqual(cityCalls, [
    "clear",
    ["highlight", ["indexer.py"]],
    ["impact", "target"],
  ]);
});

test("history, diagnostics, and related-test tools update their shared projections", async () => {
  const workspace = createWorkspaceStore({ repoId: "demo" });
  const cityCalls = [];
  const city = {
    showHistory: (result) => cityCalls.push(["history", result.path]),
    showDiagnostics: (result) => cityCalls.push(["diagnostics", result.findings.length]),
    showRelatedTests: (paths) => cityCalls.push(["tests", paths]),
  };
  const registry = createWebMCPRegistry();
  const history = createExplainHistoryTool({
    api: {
      async explainHistory() {
        return {
          repo: { id: "demo" },
          result: {
            path: "service.py",
            symbol: null,
            commits: [{ hash: "a" }],
            blame: [],
            history_hint: "Initial change",
          },
          ui: { focus: { path: "service.py" }, highlights: ["service.py"], mode: "history" },
        };
      },
    },
    workspace,
    city,
    registry,
    repoId: "demo",
  });
  const diagnostics = createShowDiagnosticsTool({
    api: {
      async showDiagnostics() {
        return {
          repo: { id: "demo" },
          result: {
            paths_checked: ["service.py"],
            summary: { status: "failed", total: 1, by_severity: { error: 1 } },
            findings: [{ file: "service.py", line: 1, severity: "error", message: "bad" }],
          },
          ui: { highlights: ["service.py"], mode: "diagnostics" },
        };
      },
    },
    workspace,
    city,
    registry,
    repoId: "demo",
  });
  const relatedTests = createFindRelatedTestsTool({
    api: {
      async findRelatedTests() {
        return {
          repo: { id: "demo" },
          result: { target: "service", tests: [{ path: "tests/test_service.py", relation: "name" }] },
          ui: { highlights: ["tests/test_service.py"], mode: "tests" },
        };
      },
    },
    workspace,
    city,
    registry,
    repoId: "demo",
  });

  await history.execute({ path: "service.py" });
  await diagnostics.execute({ paths: ["service.py"] });
  await relatedTests.execute({ target: "service" });

  assert.equal(workspace.getState().activeMode, "tests");
  assert.deepEqual(workspace.getState().relatedTests.tests, [
    { path: "tests/test_service.py", relation: "name" },
  ]);
  assert.deepEqual(cityCalls, [
    ["history", "service.py"],
    ["diagnostics", 1],
    ["tests", ["tests/test_service.py"]],
  ]);
});

test("human city selection feeds the shared workspace", () => {
  const workspace = createWorkspaceStore();
  const frameListeners = new Map();
  const frame = {
    contentWindow: {},
    addEventListener(type, listener) {
      frameListeners.set(type, listener);
    },
  };
  createCityAdapter({ frame, workspace });
  const messageListener = listeners.get("message");

  messageListener({
    source: frame.contentWindow,
    origin: "http://localhost",
    data: { type: "booster-city-selection", path: "indexer.py" },
  });

  assert.equal(workspace.getState().selectedFile, "indexer.py");
});

test("contextual tools are re-registered for selection and abort the old context", async () => {
  const registrations = [];
  document.modelContext = {
    async registerTool(tool, options) {
      registrations.push({ tool, options });
    },
  };
  const workspace = createWorkspaceStore({ repoId: "demo" });
  const manager = createContextualToolManager({
    api: {
      traceImpact: async () => ({ result: { affected_files: [], callers: [], callees: [] } }),
      explainHistory: async () => ({ result: { commits: [], blame: [], history_hint: "" } }),
    },
    workspace,
    city: {},
    registry: createWebMCPRegistry(),
  });
  manager.start();
  workspace.selectFile("first.py");
  await new Promise((resolve) => setTimeout(resolve, 0));
  workspace.selectFile("second.py");
  await new Promise((resolve) => setTimeout(resolve, 0));

  assert.equal(registrations.length, 4);
  assert.equal(registrations[0].options.signal.aborted, true);
  assert.equal(registrations[1].options.signal.aborted, true);
  assert.deepEqual(manager.getCurrentSelection(), {
    repoId: "demo",
    generationId: null,
    selectedFile: "second.py",
    selectedSymbol: null,
    searchResults: [],
    highlightedFiles: [],
    highlightedEdges: [],
    activeMode: "default",
    impact: null,
    history: null,
    diagnostics: null,
    relatedTests: null,
    snapshots: [],
    snapshotComparison: null,
    architecture: null,
    lastAgentAction: null,
    error: null,
  });
  assert.deepEqual(manager.getRegisteredTools(), [
    "booster_analyze_selected_file",
    "booster_history_of_selected_file",
  ]);
  await assert.rejects(registrations[0].tool.execute(), /stale/);
  manager.stop();
});

test("snapshot comparison updates diff state and Code City", async () => {
  const workspace = createWorkspaceStore({ repoId: "demo" });
  const cityCalls = [];
  const tool = createCompareSnapshotsTool({
    api: {
      compareSnapshots: async () => ({
        repo: { id: "demo" },
        result: {
          from_snapshot: { id: "old" },
          to_snapshot: { id: "new" },
          added: ["new.py"],
          removed: ["gone.py"],
          changed: ["changed.py"],
          stable: ["stable.py"],
          connections: { added: [], removed: [], changed: [] },
          summary: { added: 1, removed: 1, changed: 1, stable: 1 },
        },
        ui: { highlights: ["new.py", "changed.py"], mode: "snapshots" },
      }),
    },
    workspace,
    city: { showSnapshotComparison: (result) => cityCalls.push(result.summary) },
    registry: createWebMCPRegistry(),
    repoId: "demo",
  });

  const response = await tool.execute({ from: "old", to: "new" });

  assert.deepEqual(workspace.getState().highlightedFiles, ["new.py", "changed.py"]);
  assert.equal(workspace.getState().snapshotComparison.removed[0], "gone.py");
  assert.deepEqual(cityCalls, [{ added: 1, removed: 1, changed: 1, stable: 1 }]);
  assert.match(response.content[0].text, /1 added/);
});

test("architecture tool switches shared mode and optional focus", async () => {
  const workspace = createWorkspaceStore({ repoId: "demo" });
  const cityCalls = [];
  const tool = createInspectArchitectureTool({
    api: {
      inspectArchitecture: async () => ({
        repo: { id: "demo" },
        result: { focus: "service.py", map: "service.py", stats: { files_indexed: 1 } },
        ui: { mode: "architecture" },
      }),
    },
    workspace,
    city: {
      setMode: (mode) => cityCalls.push(["mode", mode]),
      focusFile: (path) => cityCalls.push(["focus", path]),
    },
    registry: createWebMCPRegistry(),
    repoId: "demo",
  });

  await tool.execute({ focus: "service.py" });

  assert.equal(workspace.getState().activeMode, "architecture");
  assert.equal(workspace.getState().architecture.map, "service.py");
  assert.deepEqual(cityCalls, [["mode", "architecture"], ["focus", "service.py"]]);
});

test("generation changes clear stale browser analysis state", () => {
  const workspace = createWorkspaceStore({ repoId: "demo" });
  workspace.applyStatus({ repo_id: "demo", generation_id: "generation-one" });
  workspace.applySnapshotComparison({
    repo: { id: "demo", generation_id: "generation-one" },
    result: { added: ["new.py"], changed: [], removed: [], stable: [] },
    ui: { highlights: ["new.py"], mode: "snapshots" },
  });

  assert.equal(workspace.applyStatus({ repo_id: "demo", generation_id: "generation-two" }), true);
  assert.equal(workspace.getState().generationId, "generation-two");
  assert.equal(workspace.getState().snapshotComparison, null);
  assert.deepEqual(workspace.getState().highlightedFiles, []);
  assert.equal(workspace.getState().activeMode, "default");
});

test("city adapter rebinds Code City API after a generation reload", () => {
  let loadListener;
  const firstCalls = [];
  const secondCalls = [];
  const frame = {
    contentWindow: { BoosterCity: { focusFile: (path) => firstCalls.push(path) } },
    addEventListener: (_type, listener) => { loadListener = listener; },
  };
  const workspace = { getState: () => ({ selectedFile: null }), clearSelection() {}, selectFile() {} };
  const adapter = createCityAdapter({ frame, workspace });

  loadListener();
  adapter.focusFile("first.py");
  adapter.reset();
  frame.contentWindow = { BoosterCity: { focusFile: (path) => secondCalls.push(path) } };
  loadListener();
  adapter.focusFile("second.py");

  assert.deepEqual(firstCalls, ["first.py"]);
  assert.deepEqual(secondCalls, ["second.py"]);
});
