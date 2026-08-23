"""Детерминированный анализ metrics/logs без генерации научных выводов."""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

DEFAULT_EXTRACT = [
    "loss_trend",
    "heldout_trend",
    "collapse_signals",
    "gradient_norms",
    "state_drift",
    "settling",
    "performance",
    "anomalies",
]

EXTRACT_ALIASES: dict[str, set[str]] = {
    "loss_trend": {"loss", "ce", "cross_entropy", "train_loss", "training_loss"},
    "heldout_trend": {"heldout", "heldout_loss", "val_loss", "eval_loss", "validation_loss"},
    "collapse_signals": {
        "dominant_token",
        "dominant_token_fraction",
        "entropy",
        "collapse",
        "collapse_score",
        "top1",
        "top5",
    },
    "gradient_norms": {"gradient_norm", "grad_norm", "gradient", "grad"},
    "state_drift": {"state_drift", "drift", "state_change", "state_delta"},
    "settling": {"settling", "settling_step", "settle_step", "time_to_settle"},
    "performance": {"top1", "top5", "accuracy", "step_s", "steps_per_second", "throughput"},
}

REGIME_KEYS = {
    "eval_regime",
    "regime",
    "dataset",
    "dataset_name",
    "split",
    "eval_split",
    "sequence_length",
    "eval_tokens",
    "eval_steps",
    "batch_size",
    "temperature",
}


def _canonical(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    if isinstance(value, str):
        try:
            number = float(value.strip())
        except ValueError:
            return None
        return number if math.isfinite(number) else None
    return None


def _flatten(row: dict[str, Any], prefix: str = "") -> Iterable[tuple[str, Any]]:
    for key, value in row.items():
        name = f"{prefix}_{key}" if prefix else str(key)
        if isinstance(value, dict):
            yield from _flatten(value, name)
        else:
            yield _canonical(name), value


def read_rows(path: Path, *, max_bytes: int = 50_000) -> tuple[list[dict[str, Any]], bool, int]:
    """Читает JSON/JSONL bounded способом и возвращает invalid line count."""
    size = path.stat().st_size
    truncated = size > max_bytes
    with path.open("rb") as stream:
        if not truncated:
            raw = stream.read()
        else:
            half = max_bytes // 2
            first = stream.read(half)
            stream.seek(max(half, size - half))
            last = stream.read(half)
            raw = first + b"\n" + last
    text = raw.decode("utf-8", errors="replace")
    invalid = 0
    if path.suffix.lower() == ".json":
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return [], truncated, 1
        if isinstance(value, dict):
            return [value], truncated, 0
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)], truncated, 0
        return [], truncated, 1
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            invalid += 1
            continue
        if isinstance(value, dict):
            rows.append(value)
        else:
            invalid += 1
    return rows, truncated, invalid


def metric_series(rows: list[dict[str, Any]]) -> dict[str, list[float]]:
    series: dict[str, list[float]] = {}
    for row in rows:
        for key, value in _flatten(row):
            number = _numeric(value)
            if number is not None:
                series.setdefault(key, []).append(number)
    return series


def _field_for_extract(series: dict[str, list[float]], extract: str) -> str | None:
    aliases = EXTRACT_ALIASES.get(extract, {_canonical(extract)})
    exact = [key for key in series if key in aliases]
    if exact:
        return exact[0]
    for key in series:
        if any(alias in key or key in alias for alias in aliases):
            return key
    return None


def _trend(values: list[float]) -> dict[str, Any]:
    first = values[0]
    last = values[-1]
    delta = last - first
    scale = max(abs(first), abs(last), 1e-9)
    relative = delta / scale
    if abs(relative) <= 0.02:
        direction = "unchanged"
    elif delta > 0:
        direction = "increased"
    else:
        direction = "decreased"
    return {
        "samples": len(values),
        "first": first,
        "last": last,
        "min": min(values),
        "max": max(values),
        "delta": delta,
        "relative_delta": relative,
        "direction": direction,
    }


def regime_signature(rows: list[dict[str, Any]]) -> dict[str, Any]:
    signature: dict[str, Any] = {}
    for row in rows:
        for key, value in _flatten(row):
            if key in REGIME_KEYS and isinstance(value, (str, int, float, bool)):
                signature[key] = value
    return signature


def scientific_digest(
    rows: list[dict[str, Any]],
    extract: list[str] | None = None,
    *,
    invalid_lines: int = 0,
    truncated: bool = False,
    compare_rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    requested = extract or DEFAULT_EXTRACT
    series = metric_series(rows)
    observed: list[dict[str, Any]] = []
    increased: list[dict[str, Any]] = []
    decreased: list[dict[str, Any]] = []
    unchanged: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []
    for item in requested:
        if item == "anomalies":
            continue
        field = _field_for_extract(series, item)
        if field is None:
            unchanged.append({"metric": item, "status": "not_observed"})
            continue
        trend = _trend(series[field])
        record = {"metric": item, "field": field, **trend}
        observed.append(record)
        target = {
            "increased": increased,
            "decreased": decreased,
            "unchanged": unchanged,
        }[trend["direction"]]
        target.append(record)
        values = series[field]
        if len(values) >= 4:
            baseline = max(abs(values[0]), 1e-9)
            for index, value in enumerate(values[1:], start=1):
                if abs(value - values[index - 1]) > baseline * 5:
                    anomalies.append(
                        {
                            "metric": item,
                            "field": field,
                            "sample": index,
                            "value": value,
                            "reason": "sudden_jump",
                        }
                    )
                    break
    if invalid_lines:
        anomalies.append({"reason": "invalid_json_lines", "count": invalid_lines})
    if truncated:
        anomalies.append({"reason": "raw_log_truncated_before_analysis"})
    for key, values in series.items():
        if len(values) < len(rows):
            missing = len(rows) - len(values)
            if missing > max(1, len(rows) // 3):
                anomalies.append({"field": key, "reason": "missing_values", "count": missing})

    confounds: list[dict[str, Any]] = []
    comparison: dict[str, Any] = {}
    current_regime = regime_signature(rows)
    if compare_rows is not None:
        baseline_regime = regime_signature(compare_rows)
        baseline_series = metric_series(compare_rows)
        for record in observed:
            baseline_field = record["field"]
            baseline_values = baseline_series.get(baseline_field, [])
            comparison[record["metric"]] = {
                "baseline_field": baseline_field,
                "baseline_last": baseline_values[-1] if baseline_values else None,
                "current_last": record["last"],
                "delta_vs_baseline": (
                    record["last"] - baseline_values[-1] if baseline_values else None
                ),
            }
        if current_regime != baseline_regime:
            confounds.append(
                {
                    "reason": "eval_regime_differs",
                    "current": current_regime,
                    "baseline": baseline_regime,
                }
            )
    if not current_regime:
        confounds.append({"reason": "eval_regime_not_recorded"})
    return {
        "OBSERVED": observed,
        "INCREASED": increased,
        "DECREASED": decreased,
        "UNCHANGED": unchanged,
        "ANOMALIES": anomalies,
        "POSSIBLE_CONFOUNDS": confounds,
        "metrics": {key: _trend(values) for key, values in series.items()},
        "comparison": comparison,
        "rows": len(rows),
        "eval_regime": current_regime,
    }


def compare_run_records(
    records: list[dict[str, Any]],
    metrics: list[str],
    *,
    normalize_eval_regime: bool,
) -> dict[str, Any]:
    """Сравнивает только совместимые eval regimes."""
    normalized_metrics = [_canonical(metric) for metric in metrics]
    regimes = [record.get("regime", {}) for record in records]
    comparable = True
    if normalize_eval_regime and regimes:
        comparable = bool(regimes[0]) and all(regime == regimes[0] for regime in regimes[1:])
    status = "COMPARABLE" if comparable else "NOT DIRECTLY COMPARABLE"
    values: dict[str, dict[str, float | None]] = {}
    warnings: list[str] = []
    for metric in normalized_metrics:
        metric_values: dict[str, float | None] = {}
        for record in records:
            series = record.get("series", {})
            field = (
                metric
                if metric in series
                else next((key for key in series if metric in key or key in metric), None)
            )
            metric_values[str(record.get("run"))] = (
                series[field][-1] if field and series.get(field) else None
            )
        values[metric] = metric_values
    comparisons: dict[str, Any] = {}
    if comparable and records:
        baseline = str(records[0].get("run"))
        for metric, metric_values in values.items():
            base = metric_values.get(baseline)
            comparisons[metric] = {
                "baseline": baseline,
                "delta_vs_baseline": {
                    run: (value - base if value is not None and base is not None else None)
                    for run, value in metric_values.items()
                },
            }
    else:
        reason = "eval regimes differ" if all(regimes) else "eval regime is missing"
        warnings.append(f"NOT DIRECTLY COMPARABLE: {reason}")
    return {
        "status": status,
        "comparable": comparable,
        "regimes": regimes,
        "values": values,
        "comparisons": comparisons,
        "warnings": warnings,
    }


__all__ = [
    "DEFAULT_EXTRACT",
    "compare_run_records",
    "read_rows",
    "regime_signature",
    "scientific_digest",
]
