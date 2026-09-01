class BoosterApiError extends Error {
  constructor(code, message, retryable = false, status = 500) {
    super(message);
    this.name = "BoosterApiError";
    this.code = code;
    this.retryable = retryable;
    this.status = status;
  }
}

async function requestJson(url, options = {}) {
  let response;
  try {
    response = await fetch(url, {
      ...options,
      headers: { Accept: "application/json", ...(options.headers || {}) },
    });
  } catch (_error) {
    throw new BoosterApiError("INTERNAL_ERROR", "Booster API is unavailable", true, 0);
  }

  let payload;
  try {
    payload = await response.json();
  } catch (_error) {
    throw new BoosterApiError("INTERNAL_ERROR", "Booster API returned invalid JSON", true, response.status);
  }
  if (!response.ok || payload?.ok === false) {
    const error = payload?.error || {};
    throw new BoosterApiError(
      error.code || "INTERNAL_ERROR",
      error.message || "Booster API request failed",
      Boolean(error.retryable),
      response.status,
    );
  }
  return payload;
}

const boosterApi = {
  status(repoId = null) {
    const suffix = repoId ? `?repo_id=${encodeURIComponent(repoId)}` : "";
    return requestJson(`/api/v1/status${suffix}`);
  },
  focusSymbol(repoId, symbol) {
    return requestJson("/api/v1/symbol/focus", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_id: repoId, query: symbol }),
    });
  },
  searchCode(repoId, query, limit = 8) {
    return requestJson("/api/v1/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_id: repoId, query, limit }),
    });
  },
  traceImpact(repoId, target, maxDepth = 3) {
    return requestJson("/api/v1/impact", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_id: repoId, target, max_depth: maxDepth }),
    });
  },
  explainHistory(repoId, { path = null, symbol = null, limit = 8 } = {}) {
    return requestJson("/api/v1/history", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_id: repoId, path, symbol, limit }),
    });
  },
  showDiagnostics(repoId, paths) {
    return requestJson("/api/v1/diagnostics", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_id: repoId, paths }),
    });
  },
  findRelatedTests(repoId, target, limit = 8) {
    return requestJson("/api/v1/related-tests", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_id: repoId, target, limit }),
    });
  },
  listSnapshots(repoId, limit = 20) {
    return requestJson(`/api/v1/snapshots?repo_id=${encodeURIComponent(repoId)}&limit=${limit}`);
  },
  compareSnapshots(repoId, fromId, toId) {
    return requestJson("/api/v1/snapshots/compare", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_id: repoId, from: fromId, to: toId }),
    });
  },
  inspectArchitecture(repoId, focus = null) {
    return requestJson("/api/v1/architecture", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ repo_id: repoId, focus }),
    });
  },
};

if (typeof window !== "undefined") {
  window.BoosterApi = boosterApi;
  window.BoosterApiError = BoosterApiError;
}

export { BoosterApiError, boosterApi, requestJson };
