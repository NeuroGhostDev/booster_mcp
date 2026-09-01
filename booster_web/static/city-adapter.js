function createCityAdapter({ frame = null, workspace }) {
  let cityApi = null;
  let frameReady = !frame;
  let pendingFocusPath = null;
  let pendingHighlights = null;
  let pendingImpact = null;
  let pendingDiagnostics = null;
  let pendingSnapshotComparison = null;

  function flushPending() {
    if (!cityApi) return;
    if (pendingImpact !== null) {
      const result = pendingImpact;
      pendingImpact = null;
      cityApi.showImpact?.(result);
    }
    if (pendingDiagnostics !== null) {
      const result = pendingDiagnostics;
      pendingDiagnostics = null;
      cityApi.showDiagnostics?.(result);
    }
    if (pendingSnapshotComparison !== null) {
      const result = pendingSnapshotComparison;
      pendingSnapshotComparison = null;
      (cityApi.showSnapshotDiff || cityApi.showSnapshotComparison)?.(result);
    }
    if (pendingFocusPath) {
      const path = pendingFocusPath;
      pendingFocusPath = null;
      cityApi.focusFile?.(path);
    }
    if (pendingHighlights !== null) {
      const paths = pendingHighlights;
      pendingHighlights = null;
      cityApi.highlightFiles?.(paths);
    }
  }

  function resolveApi() {
    if (frame && !frameReady) return null;
    if (frame?.contentWindow?.BoosterCity) cityApi = frame.contentWindow.BoosterCity;
    if (!cityApi && typeof window !== "undefined" && window.BoosterCity) {
      cityApi = window.BoosterCity;
    }
    flushPending();
    return cityApi;
  }

  function onFrameLoad() {
    frameReady = true;
    cityApi = frame?.contentWindow?.BoosterCity || null;
    resolveApi();
  }

  function onMessage(event) {
    if (!frame?.contentWindow || event.source !== frame.contentWindow) return;
    if (event.origin !== window.location.origin) return;
    const data = event.data;
    if (data?.type !== "booster-city-selection") return;
    if (data.path === null) {
      workspace.clearSelection();
      return;
    }
    if (typeof data.path !== "string") return;
    workspace.selectFile(data.path, data.symbol || null, "human");
  }

  if (frame) {
    frame.addEventListener("load", onFrameLoad);
    window.addEventListener("message", onMessage);
  }

  return {
    setCityApi(api) {
      cityApi = api || null;
      if (api) frameReady = true;
      flushPending();
    },
    reset() {
      cityApi = null;
      frameReady = !frame;
      pendingFocusPath = null;
      pendingHighlights = null;
      pendingImpact = null;
      pendingDiagnostics = null;
      pendingSnapshotComparison = null;
      return true;
    },
    getSelection() {
      return resolveApi()?.getSelection?.() || workspace.getState().selectedFile;
    },
    setMode(mode) {
      return Boolean(resolveApi()?.setMode?.(mode));
    },
    selectFile(path) {
      return Boolean(resolveApi()?.selectFile?.(path));
    },
    focusFile(path) {
      const api = resolveApi();
      if (!api?.focusFile) {
        pendingFocusPath = path;
        return true;
      }
      return Boolean(api.focusFile(path));
    },
    highlightFiles(paths) {
      const values = Array.isArray(paths) ? paths : [];
      pendingImpact = null;
      pendingDiagnostics = null;
      pendingSnapshotComparison = null;
      const api = resolveApi();
      if (!api?.highlightFiles) {
        pendingHighlights = values;
        return true;
      }
      return Boolean(api.highlightFiles(values));
    },
    clearHighlights() {
      pendingImpact = null;
      pendingDiagnostics = null;
      pendingSnapshotComparison = null;
      pendingHighlights = [];
      return Boolean(resolveApi()?.clearHighlights?.());
    },
    showImpact(result) {
      pendingDiagnostics = null;
      if (!resolveApi()?.showImpact) {
        pendingImpact = result;
        pendingHighlights = null;
        pendingFocusPath = null;
        return true;
      }
      return Boolean(resolveApi()?.showImpact?.(result));
    },
    showHistory(result) {
      const path = result?.path;
      const api = resolveApi();
      if (api?.showHistory) {
        return Boolean(api.showHistory(result));
      }
      if (!path) return false;
      this.highlightFiles?.([path]);
      this.focusFile?.(path);
      return true;
    },
    showDiagnostics(result) {
      pendingImpact = null;
      pendingSnapshotComparison = null;
      const api = resolveApi();
      if (!api?.showDiagnostics) {
        pendingDiagnostics = result;
        pendingHighlights = null;
        return true;
      }
      return Boolean(api.showDiagnostics(result));
    },
    showSnapshotDiff(result) {
      pendingImpact = null;
      pendingDiagnostics = null;
      const api = resolveApi();
      const showDiff = api?.showSnapshotDiff || api?.showSnapshotComparison;
      if (!showDiff) {
        pendingSnapshotComparison = result;
        pendingHighlights = null;
        return true;
      }
      return Boolean(showDiff.call(api, result));
    },
    showSnapshotComparison(result) {
      return this.showSnapshotDiff(result);
    },
    showRelatedTests(paths, targetPath = null) {
      const api = resolveApi();
      if (api?.showRelatedTests) return Boolean(api.showRelatedTests(paths, targetPath));
      return Boolean(this.highlightFiles?.(paths));
    },
    clearSelection() {
      return Boolean(resolveApi()?.clearSelection?.());
    },
    resetView() {
      return Boolean(resolveApi()?.resetView?.());
    },
    dispose() {
      if (frame) window.removeEventListener("message", onMessage);
    },
  };
}

if (typeof window !== "undefined") {
  window.createBoosterCityAdapter = createCityAdapter;
}

export { createCityAdapter };
