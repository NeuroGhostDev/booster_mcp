function createFocusSymbolTool({ api, workspace, city, registry, repoId }) {
  const resolveRepoId = () =>
    (typeof repoId === "function" ? repoId() : repoId) || workspace.getState().repoId;

  return {
    name: "booster_focus_symbol",
    description: "Find a code symbol in the current repository and focus its file in Booster Code City.",
    inputSchema: {
      type: "object",
      properties: {
        symbol: { type: "string", minLength: 1 },
      },
      required: ["symbol"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true },
    async execute(args) {
      const symbol = typeof args?.symbol === "string" ? args.symbol.trim() : "";
      const activeRepoId = resolveRepoId();
      if (!symbol || !activeRepoId) {
        const error = new Error("A symbol and current repository are required");
        error.code = "INVALID_ARGUMENT";
        workspace.agentActionFailed("booster_focus_symbol", error, symbol);
        throw error;
      }

      workspace.agentActionStarted("booster_focus_symbol", symbol);
      const trace = registry?.beginCall?.(
        "booster_focus_symbol",
        activeRepoId,
        workspace.getState().generationId,
      );
      try {
        const response = await api.focusSymbol(activeRepoId, symbol);
        workspace.applyFocusResult(response);
        const path = response.result.symbol.path;
        city?.focusFile?.(path);
        const durationMs = trace ? registry.finishCall(trace, "completed", 1) : undefined;
        workspace.agentActionSucceeded("booster_focus_symbol", {
          symbol,
          durationMs,
        });
        return {
          content: [
            {
              type: "text",
              text: `Found ${response.result.symbol.name} in ${path}:${response.result.symbol.line}. The file is now selected and focused in Booster Code City.`,
            },
          ],
        };
      } catch (error) {
        if (trace) registry.finishCall(trace, "failed", 0);
        workspace.agentActionFailed("booster_focus_symbol", error, symbol);
        throw error;
      }
    },
  };
}

function toolArgumentError(message) {
  const error = new Error(message);
  error.code = "INVALID_ARGUMENT";
  return error;
}

function createSearchCodeTool({ api, workspace, city, registry, repoId }) {
  const resolveRepoId = () =>
    (typeof repoId === "function" ? repoId() : repoId) || workspace.getState().repoId;

  return {
    name: "booster_search_code",
    description: "Search the current repository and highlight matching files in Booster Code City.",
    inputSchema: {
      type: "object",
      properties: {
        query: { type: "string", minLength: 2 },
        limit: { type: "integer", minimum: 1, maximum: 20, default: 8 },
      },
      required: ["query"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true },
    async execute(args) {
      const query = typeof args?.query === "string" ? args.query.trim() : "";
      const limit = args?.limit === undefined ? 8 : args.limit;
      const activeRepoId = resolveRepoId();
      if (query.length < 2 || !Number.isInteger(limit) || limit < 1 || limit > 20) {
        const error = toolArgumentError(
          "A query of at least two characters and a limit from 1 to 20 are required",
        );
        workspace.agentActionFailed("booster_search_code", error, query);
        throw error;
      }
      if (!activeRepoId) {
        const error = toolArgumentError("A current repository is required");
        workspace.agentActionFailed("booster_search_code", error, query);
        throw error;
      }

      workspace.agentActionStarted("booster_search_code", query);
      const trace = registry?.beginCall?.(
        "booster_search_code",
        activeRepoId,
        workspace.getState().generationId,
      );
      try {
        const response = await api.searchCode(activeRepoId, query, limit);
        workspace.applySearchResult(response);
        city?.clearHighlights?.();
        city?.highlightFiles?.(response.result.matches.map((match) => match.path));
        const durationMs = trace
          ? registry.finishCall(trace, "completed", response.result.matches.length)
          : undefined;
        workspace.agentActionSucceeded("booster_search_code", { symbol: query, durationMs });
        return {
          content: [
            {
              type: "text",
              text: `Found ${response.result.matches.length} matching files for "${query}". Matching files are highlighted in Booster Code City.`,
            },
          ],
        };
      } catch (error) {
        if (trace) registry.finishCall(trace, "failed", 0);
        workspace.agentActionFailed("booster_search_code", error, query);
        throw error;
      }
    },
  };
}

function createTraceImpactTool({ api, workspace, city, registry, repoId }) {
  const resolveRepoId = () =>
    (typeof repoId === "function" ? repoId() : repoId) || workspace.getState().repoId;

  return {
    name: "booster_trace_impact",
    description: "Trace a symbol or file through the repository graph and show its affected files.",
    inputSchema: {
      type: "object",
      properties: {
        target: { type: "string", description: "Symbol or file to analyze", minLength: 1 },
        max_depth: { type: "integer", minimum: 1, maximum: 4, default: 3 },
      },
      required: ["target"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true },
    async execute(args) {
      const target = typeof args?.target === "string" ? args.target.trim() : "";
      const maxDepth = args?.max_depth === undefined ? 3 : args.max_depth;
      const activeRepoId = resolveRepoId();
      if (!target || !Number.isInteger(maxDepth) || maxDepth < 1 || maxDepth > 4) {
        const error = toolArgumentError("A target and a max_depth from 1 to 4 are required");
        workspace.agentActionFailed("booster_trace_impact", error, target);
        throw error;
      }
      if (!activeRepoId) {
        const error = toolArgumentError("A current repository is required");
        workspace.agentActionFailed("booster_trace_impact", error, target);
        throw error;
      }

      workspace.agentActionStarted("booster_trace_impact", target);
      const trace = registry?.beginCall?.(
        "booster_trace_impact",
        activeRepoId,
        workspace.getState().generationId,
      );
      try {
        const response = await api.traceImpact(activeRepoId, target, maxDepth);
        workspace.applyImpactResult(response);
        if (city?.showImpact) city.showImpact(response.result);
        else {
          city?.clearHighlights?.();
          city?.highlightFiles?.(response.result.affected_files);
          if (response.result.target_file) city?.focusFile?.(response.result.target_file);
        }
        const result = response.result;
        const durationMs = trace
          ? registry.finishCall(trace, "completed", result.affected_files.length)
          : undefined;
        workspace.agentActionSucceeded("booster_trace_impact", { symbol: target, durationMs });
        return {
          content: [
            {
              type: "text",
              text: `Impact for ${result.target}: ${result.affected_files.length} affected files, ${result.callers.length} callers, ${result.callees.length} callees, and ${result.tests.length} tests.`,
            },
          ],
        };
      } catch (error) {
        if (trace) registry.finishCall(trace, "failed", 0);
        workspace.agentActionFailed("booster_trace_impact", error, target);
        throw error;
      }
    },
  };
}

function createExplainHistoryTool({ api, workspace, city, registry, repoId }) {
  const resolveRepoId = () =>
    (typeof repoId === "function" ? repoId() : repoId) || workspace.getState().repoId;

  return {
    name: "booster_explain_history",
    description: "Explain the git history of a repository file or symbol in Booster Observatory.",
    inputSchema: {
      type: "object",
      properties: {
        path: { type: "string", minLength: 1 },
        symbol: { type: "string", minLength: 1 },
        limit: { type: "integer", minimum: 1, maximum: 20, default: 8 },
      },
      anyOf: [{ required: ["path"] }, { required: ["symbol"] }],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true },
    async execute(args) {
      const path = typeof args?.path === "string" ? args.path.trim() : "";
      const symbol = typeof args?.symbol === "string" ? args.symbol.trim() : "";
      const limit = args?.limit === undefined ? 8 : args.limit;
      const activeRepoId = resolveRepoId();
      if ((!path && !symbol) || !Number.isInteger(limit) || limit < 1 || limit > 20) {
        const error = toolArgumentError("A path or symbol and a limit from 1 to 20 are required");
        workspace.agentActionFailed("booster_explain_history", error, path || symbol);
        throw error;
      }
      if (!activeRepoId) {
        const error = toolArgumentError("A current repository is required");
        workspace.agentActionFailed("booster_explain_history", error, path || symbol);
        throw error;
      }

      const target = path || symbol;
      workspace.agentActionStarted("booster_explain_history", target);
      const trace = registry?.beginCall?.(
        "booster_explain_history",
        activeRepoId,
        workspace.getState().generationId,
      );
      try {
        const response = await api.explainHistory(activeRepoId, {
          path: path || null,
          symbol: symbol || null,
          limit,
        });
        workspace.applyHistoryResult(response);
        city?.showHistory?.(response.result);
        const durationMs = trace
          ? registry.finishCall(
              trace,
              "completed",
              response.result.commits.length + response.result.blame.length,
            )
          : undefined;
        workspace.agentActionSucceeded("booster_explain_history", {
          symbol: target,
          durationMs,
        });
        return {
          content: [
            {
              type: "text",
              text: `History for ${target}: ${response.result.commits.length} commits and ${response.result.blame.length} blame entries. ${response.result.history_hint}`,
            },
          ],
        };
      } catch (error) {
        if (trace) registry.finishCall(trace, "failed", 0);
        workspace.agentActionFailed("booster_explain_history", error, target);
        throw error;
      }
    },
  };
}

function createShowDiagnosticsTool({ api, workspace, city, registry, repoId }) {
  const resolveRepoId = () =>
    (typeof repoId === "function" ? repoId() : repoId) || workspace.getState().repoId;

  return {
    name: "booster_show_diagnostics",
    description: "Show read-only diagnostics for selected repository files in Booster Observatory.",
    inputSchema: {
      type: "object",
      properties: {
        paths: { type: "array", items: { type: "string", minLength: 1 }, maxItems: 20 },
      },
      required: ["paths"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true },
    async execute(args) {
      const paths = Array.isArray(args?.paths)
        ? args.paths.map((path) => (typeof path === "string" ? path.trim() : ""))
        : [];
      const activeRepoId = resolveRepoId();
      if (!paths.length || paths.length > 20 || paths.some((path) => !path)) {
        const error = toolArgumentError("Between one and twenty repository-relative paths are required");
        workspace.agentActionFailed("booster_show_diagnostics", error, paths.join(", "));
        throw error;
      }
      if (!activeRepoId) {
        const error = toolArgumentError("A current repository is required");
        workspace.agentActionFailed("booster_show_diagnostics", error, paths.join(", "));
        throw error;
      }

      const target = paths.join(", ");
      workspace.agentActionStarted("booster_show_diagnostics", target);
      const trace = registry?.beginCall?.(
        "booster_show_diagnostics",
        activeRepoId,
        workspace.getState().generationId,
      );
      try {
        const response = await api.showDiagnostics(activeRepoId, paths);
        workspace.applyDiagnosticsResult(response);
        city?.showDiagnostics?.(response.result);
        const durationMs = trace
          ? registry.finishCall(trace, "completed", response.result.findings.length)
          : undefined;
        workspace.agentActionSucceeded("booster_show_diagnostics", {
          symbol: target,
          durationMs,
        });
        return {
          content: [
            {
              type: "text",
              text: `Diagnostics: ${response.result.summary.total} findings in ${response.result.paths_checked.length} files (${response.result.summary.status}).`,
            },
          ],
        };
      } catch (error) {
        if (trace) registry.finishCall(trace, "failed", 0);
        workspace.agentActionFailed("booster_show_diagnostics", error, target);
        throw error;
      }
    },
  };
}

function createFindRelatedTestsTool({ api, workspace, city, registry, repoId }) {
  const resolveRepoId = () =>
    (typeof repoId === "function" ? repoId() : repoId) || workspace.getState().repoId;

  return {
    name: "booster_find_related_tests",
    description: "Find deterministic tests related to a repository symbol or file and highlight them in Code City.",
    inputSchema: {
      type: "object",
      properties: {
        target: { type: "string", minLength: 1 },
        limit: { type: "integer", minimum: 1, maximum: 20, default: 8 },
      },
      required: ["target"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true },
    async execute(args) {
      const target = typeof args?.target === "string" ? args.target.trim() : "";
      const limit = args?.limit === undefined ? 8 : args.limit;
      const activeRepoId = resolveRepoId();
      if (!target || !Number.isInteger(limit) || limit < 1 || limit > 20) {
        const error = toolArgumentError("A target and a limit from 1 to 20 are required");
        workspace.agentActionFailed("booster_find_related_tests", error, target);
        throw error;
      }
      if (!activeRepoId) {
        const error = toolArgumentError("A current repository is required");
        workspace.agentActionFailed("booster_find_related_tests", error, target);
        throw error;
      }

      workspace.agentActionStarted("booster_find_related_tests", target);
      const trace = registry?.beginCall?.(
        "booster_find_related_tests",
        activeRepoId,
        workspace.getState().generationId,
      );
      try {
        const response = await api.findRelatedTests(activeRepoId, target, limit);
        workspace.applyRelatedTestsResult(response);
        city?.showRelatedTests?.(
          response.result.tests.map((item) => item.path),
          workspace.getState().selectedFile,
        );
        const durationMs = trace
          ? registry.finishCall(trace, "completed", response.result.tests.length)
          : undefined;
        workspace.agentActionSucceeded("booster_find_related_tests", {
          symbol: target,
          durationMs,
        });
        return {
          content: [
            {
              type: "text",
              text: `Found ${response.result.tests.length} related tests for ${target}. Tests are highlighted in Booster Code City.`,
            },
          ],
        };
      } catch (error) {
        if (trace) registry.finishCall(trace, "failed", 0);
        workspace.agentActionFailed("booster_find_related_tests", error, target);
        throw error;
      }
    },
  };
}

function createCompareSnapshotsTool({ api, workspace, city, registry, repoId }) {
  const resolveRepoId = () =>
    (typeof repoId === "function" ? repoId() : repoId) || workspace.getState().repoId;

  return {
    name: "booster_compare_snapshots",
    description: "Compare two immutable Booster repository snapshots and update Code City diff state.",
    inputSchema: {
      type: "object",
      properties: {
        from: { type: "string", minLength: 1 },
        to: { type: "string", minLength: 1 },
      },
      required: ["from", "to"],
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true },
    async execute(args) {
      const fromId = typeof args?.from === "string" ? args.from.trim() : "";
      const toId = typeof args?.to === "string" ? args.to.trim() : "";
      const activeRepoId = resolveRepoId();
      if (!fromId || !toId) {
        const error = toolArgumentError("Two snapshot IDs are required");
        workspace.agentActionFailed("booster_compare_snapshots", error, `${fromId} -> ${toId}`);
        throw error;
      }
      if (!activeRepoId) {
        const error = toolArgumentError("A current repository is required");
        workspace.agentActionFailed("booster_compare_snapshots", error, `${fromId} -> ${toId}`);
        throw error;
      }

      const target = `${fromId} -> ${toId}`;
      workspace.agentActionStarted("booster_compare_snapshots", target);
      const trace = registry?.beginCall?.(
        "booster_compare_snapshots",
        activeRepoId,
        workspace.getState().generationId,
      );
      try {
        const response = await api.compareSnapshots(activeRepoId, fromId, toId);
        workspace.applySnapshotComparison(response);
        city?.showSnapshotComparison?.(response.result);
        const summary = response.result.summary;
        const resultCount = Object.values(summary || {}).reduce(
          (total, value) => total + (Number.isFinite(value) ? value : 0),
          0,
        );
        const durationMs = trace
          ? registry.finishCall(trace, "completed", resultCount)
          : undefined;
        workspace.agentActionSucceeded("booster_compare_snapshots", {
          symbol: target,
          durationMs,
        });
        return {
          content: [
            {
              type: "text",
              text: `Compared snapshots ${fromId} and ${toId}: ${summary.added || 0} added, ${summary.removed || 0} removed, ${summary.changed || 0} changed, ${summary.stable || 0} stable, ${summary.unverified || 0} unverified.`,
            },
          ],
        };
      } catch (error) {
        if (trace) registry.finishCall(trace, "failed", 0);
        workspace.agentActionFailed("booster_compare_snapshots", error, target);
        throw error;
      }
    },
  };
}

function createInspectArchitectureTool({ api, workspace, city, registry, repoId }) {
  const resolveRepoId = () =>
    (typeof repoId === "function" ? repoId() : repoId) || workspace.getState().repoId;

  return {
    name: "booster_inspect_architecture",
    description: "Show the repository architecture overview and switch Booster Code City to architecture mode.",
    inputSchema: {
      type: "object",
      properties: {
        focus: { type: "string", minLength: 1, description: "Optional architecture area or module to focus on" },
      },
      additionalProperties: false,
    },
    annotations: { readOnlyHint: true },
    async execute(args = {}) {
      const focus = typeof args.focus === "string" ? args.focus.trim() : null;
      const activeRepoId = resolveRepoId();
      if (args.focus !== undefined && !focus) {
        const error = toolArgumentError("Architecture focus must not be blank");
        workspace.agentActionFailed("booster_inspect_architecture", error, "architecture");
        throw error;
      }
      if (!activeRepoId) {
        const error = toolArgumentError("A current repository is required");
        workspace.agentActionFailed("booster_inspect_architecture", error, "architecture");
        throw error;
      }
      workspace.agentActionStarted("booster_inspect_architecture", focus || "architecture");
      const trace = registry?.beginCall?.(
        "booster_inspect_architecture",
        activeRepoId,
        workspace.getState().generationId,
      );
      try {
        const response = await api.inspectArchitecture(activeRepoId, focus);
        workspace.applyArchitectureResult(response);
        city?.setMode?.("architecture");
        if (focus) city?.focusFile?.(focus);
        const durationMs = trace ? registry.finishCall(trace, "completed", 1) : undefined;
        workspace.agentActionSucceeded("booster_inspect_architecture", {
          symbol: focus || "architecture",
          durationMs,
        });
        return {
          content: [
            {
              type: "text",
              text: `Architecture overview loaded${focus ? ` for ${focus}` : ""}. Code City is now in architecture mode.`,
            },
          ],
        };
      } catch (error) {
        if (trace) registry.finishCall(trace, "failed", 0);
        workspace.agentActionFailed("booster_inspect_architecture", error, focus || "architecture");
        throw error;
      }
    },
  };
}

if (typeof window !== "undefined") {
  window.createBoosterFocusSymbolTool = createFocusSymbolTool;
  window.createBoosterSearchCodeTool = createSearchCodeTool;
  window.createBoosterTraceImpactTool = createTraceImpactTool;
  window.createBoosterExplainHistoryTool = createExplainHistoryTool;
  window.createBoosterShowDiagnosticsTool = createShowDiagnosticsTool;
  window.createBoosterFindRelatedTestsTool = createFindRelatedTestsTool;
  window.createBoosterCompareSnapshotsTool = createCompareSnapshotsTool;
  window.createBoosterInspectArchitectureTool = createInspectArchitectureTool;
}

export {
  createFocusSymbolTool,
  createSearchCodeTool,
  createTraceImpactTool,
  createExplainHistoryTool,
  createShowDiagnosticsTool,
  createFindRelatedTestsTool,
  createCompareSnapshotsTool,
  createInspectArchitectureTool,
};
