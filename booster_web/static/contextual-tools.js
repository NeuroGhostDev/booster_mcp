function selectionIsCurrent(workspace, selection) {
  const state = workspace.getState();
  return state.repoId === selection.repoId && state.selectedFile === selection.selectedFile;
}

function createAnalyzeSelectedFileTool({ api, workspace, city, registry, selection }) {
  const repoId = selection.repoId;
  const path = selection.selectedFile;
  return {
    name: "booster_analyze_selected_file",
    description: "Analyze the currently selected file and show its impact in Booster Observatory.",
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true },
    async execute() {
      if (!selectionIsCurrent(workspace, selection)) {
        const error = new Error("Selected file context is stale");
        error.code = "INVALID_ARGUMENT";
        workspace.agentActionFailed("booster_analyze_selected_file", error, path);
        throw error;
      }
      workspace.agentActionStarted("booster_analyze_selected_file", path);
      const trace = registry?.beginCall?.(
        "booster_analyze_selected_file",
        repoId,
        workspace.getState().generationId,
      );
      try {
        const response = await api.traceImpact(repoId, path, 3);
        workspace.applyImpactResult(response);
        city?.showImpact?.(response.result);
        const result = response.result;
        const durationMs = trace
          ? registry.finishCall(trace, "completed", result.affected_files.length)
          : undefined;
        workspace.agentActionSucceeded("booster_analyze_selected_file", {
          symbol: path,
          durationMs,
        });
        return {
          content: [
            {
              type: "text",
              text: `Analyzed selected file ${path}: ${result.affected_files.length} affected files, ${result.callers.length} callers, and ${result.callees.length} callees.`,
            },
          ],
        };
      } catch (error) {
        if (trace) registry.finishCall(trace, "failed", 0);
        workspace.agentActionFailed("booster_analyze_selected_file", error, path);
        throw error;
      }
    },
  };
}

function createHistoryOfSelectedFileTool({ api, workspace, city, registry, selection }) {
  const repoId = selection.repoId;
  const path = selection.selectedFile;
  return {
    name: "booster_history_of_selected_file",
    description: "Show git history and blame for the currently selected file in Booster Observatory.",
    inputSchema: {
      type: "object",
      properties: {},
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true },
    async execute() {
      if (!selectionIsCurrent(workspace, selection)) {
        const error = new Error("Selected file context is stale");
        error.code = "INVALID_ARGUMENT";
        workspace.agentActionFailed("booster_history_of_selected_file", error, path);
        throw error;
      }
      workspace.agentActionStarted("booster_history_of_selected_file", path);
      const trace = registry?.beginCall?.(
        "booster_history_of_selected_file",
        repoId,
        workspace.getState().generationId,
      );
      try {
        const response = await api.explainHistory(repoId, { path, limit: 8 });
        workspace.applyHistoryResult(response);
        city?.showHistory?.(response.result);
        const durationMs = trace
          ? registry.finishCall(
              trace,
              "completed",
              response.result.commits.length + response.result.blame.length,
            )
          : undefined;
        workspace.agentActionSucceeded("booster_history_of_selected_file", {
          symbol: path,
          durationMs,
        });
        return {
          content: [
            {
              type: "text",
              text: `History for selected file ${path}: ${response.result.commits.length} commits and ${response.result.blame.length} blame entries.`,
            },
          ],
        };
      } catch (error) {
        if (trace) registry.finishCall(trace, "failed", 0);
        workspace.agentActionFailed("booster_history_of_selected_file", error, path);
        throw error;
      }
    },
  };
}

function createContextualToolManager({ api, workspace, city, registry, onStatus = () => {} }) {
  let controller = null;
  let unsubscribe = null;
  let generation = 0;
  let currentSelection = null;
  let currentToolNames = [];

  function abortCurrent() {
    if (controller) {
      controller.abort();
      controller = null;
    }
    currentToolNames = [];
  }

  async function refresh(selection) {
    currentSelection = selection?.repoId && selection?.selectedFile ? { ...selection } : null;
    const refreshGeneration = ++generation;
    abortCurrent();
    if (!currentSelection || !registry.hasWebMCP()) {
      onStatus(currentSelection ? "unavailable" : "idle");
      return [];
    }

    controller = new AbortController();
    const tools = [
      createAnalyzeSelectedFileTool({ api, workspace, city, registry, selection: currentSelection }),
      createHistoryOfSelectedFileTool({ api, workspace, city, registry, selection: currentSelection }),
    ];
    try {
      for (const tool of tools) {
        await document.modelContext.registerTool(tool, { signal: controller.signal });
        if (refreshGeneration !== generation) return [];
      }
      currentToolNames = tools.map((tool) => tool.name);
      onStatus("active");
      return [...currentToolNames];
    } catch (error) {
      if (controller?.signal.aborted || refreshGeneration !== generation) return [];
      onStatus("error");
      throw error;
    }
  }

  function start() {
    if (unsubscribe) return;
    unsubscribe = workspace.subscribe((state, eventName) => {
      if (eventName === "booster:selection-changed" || eventName === "booster:generation-changed") {
        void refresh(state).catch(() => onStatus("error"));
      }
    });
    if (workspace.getState().selectedFile) {
      void refresh(workspace.getState()).catch(() => onStatus("error"));
    }
  }

  function stop() {
    generation += 1;
    abortCurrent();
    unsubscribe?.();
    unsubscribe = null;
    currentSelection = null;
    onStatus("idle");
  }

  return {
    start,
    stop,
    refresh,
    getCurrentSelection: () => (currentSelection ? { ...currentSelection } : null),
    getRegisteredTools: () => [...currentToolNames],
  };
}

if (typeof window !== "undefined") {
  window.createBoosterContextualToolManager = createContextualToolManager;
}

export {
  createAnalyzeSelectedFileTool,
  createContextualToolManager,
  createHistoryOfSelectedFileTool,
};
