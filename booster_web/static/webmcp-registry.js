function hasWebMCP() {
  return Boolean(
    typeof document !== "undefined" &&
      document.modelContext &&
      typeof document.modelContext.registerTool === "function",
  );
}

function createWebMCPRegistry({ onStatus = () => {}, logger = console } = {}) {
  let controller = null;
  let registeredTools = [];

  function log(event, details = {}) {
    const payload = { event, ...details };
    try {
      logger.info?.("[booster-webmcp]", payload);
    } catch (_error) {
      // Logging must never affect the application surface.
    }
  }

  async function registerTools(tools) {
    stop();
    if (!hasWebMCP()) {
      onStatus("unavailable");
      log("unavailable");
      return [];
    }

    controller = new AbortController();
    registeredTools = [];
    try {
      for (const tool of tools) {
        await document.modelContext.registerTool(tool, { signal: controller.signal });
        registeredTools.push(tool.name);
        log("registered", { tool: tool.name });
      }
      onStatus("active");
    } catch (error) {
      onStatus("error");
      log("registration-failed", { message: error?.message || "registration failed" });
      stop();
      throw error;
    }
    return [...registeredTools];
  }

  function stop() {
    if (controller) {
      controller.abort();
      log("aborted");
    }
    controller = null;
    registeredTools = [];
  }

  function beginCall(tool, repoId, generationId = null) {
    return {
      callId: globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      tool,
      repoId: repoId || null,
      generation_id: generationId || null,
      startedAt: performance.now(),
      startedAtIso: new Date().toISOString(),
    };
  }

  function finishCall(trace, status, resultCount = 0) {
    const durationMs = Math.max(0, Math.round(performance.now() - trace.startedAt));
    log("call", {
      call_id: trace.callId,
      tool: trace.tool,
      repo_id: trace.repoId,
      generation_id: trace.generation_id,
      started_at: trace.startedAtIso,
      duration_ms: durationMs,
      status,
      result_count: resultCount,
    });
    return durationMs;
  }

  return {
    hasWebMCP,
    registerTools,
    stop,
    beginCall,
    finishCall,
    getRegisteredTools: () => [...registeredTools],
  };
}

if (typeof window !== "undefined") {
  window.hasBoosterWebMCP = hasWebMCP;
  window.createBoosterWebMCPRegistry = createWebMCPRegistry;
}

export { createWebMCPRegistry, hasWebMCP };
