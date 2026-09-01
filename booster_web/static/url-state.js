const SAFE_MODE_VALUES = new Set([
  "default",
  "search",
  "impact",
  "history",
  "diagnostics",
  "tests",
  "snapshots",
  "architecture",
]);
const SAFE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/;

function safeUrlValue(value, { path = false } = {}) {
  if (typeof value !== "string" || !value || value.includes("\0")) return null;
  if (path) {
    const normalized = value.replace(/\\/g, "/");
    if (normalized.startsWith("/") || normalized.split("/").includes("..")) return null;
    return normalized;
  }
  return SAFE_ID.test(value) ? value : null;
}

function readBoosterUrlState(url = window.location.href) {
  const params = new URL(url).searchParams;
  const mode = params.get("mode");
  return {
    repoId: safeUrlValue(params.get("repo_id")),
    selectedFile: safeUrlValue(params.get("file"), { path: true }),
    mode: SAFE_MODE_VALUES.has(mode) ? mode : null,
    fromSnapshot: safeUrlValue(params.get("from")),
    toSnapshot: safeUrlValue(params.get("to")),
  };
}

function writeBoosterUrlState(state, { replace = true } = {}) {
  const url = new URL(window.location.href);
  const params = url.searchParams;
  ["repo_id", "file", "mode", "from", "to"].forEach((key) => params.delete(key));
  const repoId = safeUrlValue(state.repoId);
  const selectedFile = safeUrlValue(state.selectedFile, { path: true });
  if (repoId) params.set("repo_id", repoId);
  if (selectedFile) params.set("file", selectedFile);
  if (SAFE_MODE_VALUES.has(state.activeMode)) params.set("mode", state.activeMode);
  const comparison = state.snapshotComparison;
  const fromId = comparison?.from?.id || comparison?.from_snapshot?.id;
  const toId = comparison?.to?.id || comparison?.to_snapshot?.id;
  if (safeUrlValue(fromId) && safeUrlValue(toId)) {
    params.set("from", fromId);
    params.set("to", toId);
  }
  const method = replace ? "replaceState" : "pushState";
  window.history[method]({}, "", `${url.pathname}${url.search}${url.hash}`);
  return url.toString();
}

if (typeof window !== "undefined") {
  window.readBoosterUrlState = readBoosterUrlState;
  window.writeBoosterUrlState = writeBoosterUrlState;
}

export { readBoosterUrlState, writeBoosterUrlState };
