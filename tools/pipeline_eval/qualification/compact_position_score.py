"""Seal all interventions before joining the survey and scoring in both calibration arms."""

import argparse
from collections import defaultdict
from pathlib import Path

import numpy as np

from .. import corpus
from ..scoring import ARMS, distance_km, validate_result
from ..variants import v5_orbit_domain
from .blind_compact_score import verified_request
from .compact_position_diagnosis import FAST, OUT, TRACE_CASES, WORK, panel, prior_outcome, receipt
from .full_v5_check import _sha
from .reverse_glrt_reference import read_bound
from .reverse_glrt_report import read, write_csv


def inventory(cases, include_traces=True):
    predictions, lock = {}, []
    for case in cases:
        name = case["id"]
        for method in panel.METHODS:
            baseline, src = receipt(case, method)
            predictions[name, method, "stock"] = read(src / "prediction.json")
            modes = []
            if method in FAST:
                modes.extend(["original_frequency", "local_frequency"])
                local = prior_outcome(WORK / name / method / "local_frequency")
                if not local:
                    raise ValueError(f"local receiver pending for {name} {method}")
                if local["reason"] == "ValueError: " + v5_orbit_domain.OUTSIDE:
                    modes.append("local_orbit_support")
                if baseline.get("reason") == "ValueError: " + v5_orbit_domain.OUTSIDE:
                    modes.append("orbit_support")
                else:
                    predictions[name, method, "orbit_support"] = predictions[name, method, "stock"]
            if method == "checked":
                modes.append("added_only")
            if include_traces and name in TRACE_CASES:
                modes.append("trace")
            if include_traces and name == "DS26-0289" and method == "original":
                modes.append("previous_orbit_failure")
            if name == "DS26-0289":
                modes.append("history_support")
            for mode in modes:
                path = WORK / name / method / mode
                r = prior_outcome(path)
                if (
                    not r
                    or (r["case"], r["method"], r["mode"]) != (name, method, mode)
                    or baseline["native_sha256"] != r["inputs"][0]
                ):
                    raise ValueError(f"incomplete or unexpected replay {path}")
                pred = Path(r["prediction_path"])
                folder = pred.parent
                if not folder.is_relative_to(path) or pred.name != "prediction.json":
                    raise ValueError("replay receipt points outside its experiment")
                record = dict(
                    case=name,
                    method=method,
                    mode=mode,
                    receipt_sha256=_sha(path / "outcome.json"),
                    prediction_sha256=_sha(pred),
                    inputs=r["inputs"],
                    changed=r["changed"],
                )
                trial = read(pred)
                validate_result(trial)
                if mode in ("orbit_support", "trace", "previous_orbit_failure", "history_support"):
                    bound = read(src / "binding.json")
                    bound["job"]["output_root"] = str(folder / "solver")
                    if bound != read(folder / "solver/request.json"):
                        raise ValueError("changed solver input in a same-measurement replay")
                if mode in ("original_frequency", "local_frequency", "added_only"):
                    binding = read(folder / "binding.json")
                    record["native_sha256"] = verified_request(
                        case, read_bound(case["request"]), binding, folder / "native.json"
                    )
                    binding["job"]["output_root"] = str(folder / "solver")
                    if binding != read(folder / "solver/request.json"):
                        raise ValueError("different solver input or inference settings")
                    if mode == "local_frequency" and r["inputs"][1] != _sha(
                        WORK / name / "local-measurements.json"
                    ):
                        raise ValueError("local estimate changed after solving")
                if mode == "local_orbit_support":
                    local_dir = Path(local["prediction_path"]).parent
                    bound = read(local_dir / "binding.json")
                    expected = [
                        baseline["native_sha256"],
                        local["prediction_sha256"],
                        bound["job"]["native_input"]["sha256"],
                        _sha(OUT / "COMBINATION.md"),
                    ]
                    bound["job"]["output_root"] = str(folder / "solver")
                    if r["inputs"] != expected or bound != read(folder / "solver/request.json"):
                        raise ValueError(
                            "combined fallback does not use the corresponding local measurements"
                        )
                if mode in ("trace", "previous_orbit_failure"):
                    if trial["arms"] != predictions[name, method, "stock"]["arms"] or trial.get(
                        "reason"
                    ) != baseline.get("reason"):
                        raise ValueError(
                            "instrumentation failed to reproduce the published outcome"
                        )
                    resource = (
                        "owner-trace.json" if mode == "trace" else "previous-orbit-failure.json"
                    )
                    record["trace_sha256"] = _sha(folder / "solver" / resource)
                else:
                    predictions[name, method, mode] = trial
                if mode == "history_support":
                    if r["inputs"][1] != _sha(OUT / "HISTORY.md"):
                        raise ValueError("history retry was not bound to its protocol")
                    record["history_sha256"] = _sha(folder / "solver/history-retry.json")
                lock.append(record)
            if method in FAST and "local_orbit_support" not in modes:
                predictions[name, method, "local_orbit_support"] = predictions[
                    name, method, "local_frequency"
                ]
    panel.seal(
        OUT / "prediction-lock.json",
        dict(
            protocol_sha256=_sha(OUT / "PROTOCOL.md"),
            prior_prediction_lock_sha256=_sha(panel.OUT / "prediction-lock.json"),
            combination_protocol_sha256=_sha(OUT / "COMBINATION.md"),
            history_protocol_sha256=_sha(OUT / "HISTORY.md"),
            local_build_sha256=_sha(OUT / "local-build.json"),
            predictions=[r for r in lock if r["mode"] not in ("trace", "previous_orbit_failure")],
        ),
    )
    if include_traces:
        panel.seal(
            OUT / "trace-lock.json",
            {
                "prediction_lock_sha256": _sha(OUT / "prediction-lock.json"),
                "traces": [r for r in lock if r["mode"] in ("trace", "previous_orbit_failure")],
            },
        )
    directory = Path(__file__).parent
    sources = [
        *sorted(directory.glob("compact_position_*.py")),
        directory / "compact_history_replay.py",
        directory / "local_pilot_cfo.c",
    ]
    panel.seal(
        OUT / "source-digests.json",
        {
            "sources": {p.name: _sha(p) for p in sources},
            "raw_panel_build_sha256": _sha(panel.OUT / "build.json"),
            "prediction_lock_sha256": _sha(OUT / "prediction-lock.json"),
        },
    )
    return predictions


def score_rows(cases, predictions):
    truths = {r["id"]: r["truth"] for r in corpus.references("ds26-all159")}
    ds29 = read(panel.DS29 / "evaluation-references.json")
    for c in cases:
        if c["panel"] == "DS29":
            t = ds29[c["id"]]
            truths[c["id"]] = [t["latitude_deg"], t["longitude_deg"]]
    rows = []
    for (name, method, mode), result in predictions.items():
        for arm in ARMS:
            endpoint = result["arms"][arm]
            loc = endpoint["latlon"]
            rows.append(
                dict(
                    case=name,
                    dataset=name[:4],
                    method=method,
                    mode=mode,
                    calibration=arm,
                    status=result["status"],
                    reason=result.get("reason"),
                    error_km=distance_km(truths[name], loc),
                    rf_rms_hz=endpoint.get("rf_rms_hz"),
                    latitude_deg=loc[0] if loc else None,
                    longitude_deg=loc[1] if loc else None,
                    observations=result["metrics"].get("observations"),
                    track_count=result["metrics"].get("tracks"),
                )
            )
    return rows


def median(values):
    return float(np.median(values)) if len(values) else None


def paired_interval(shared):
    """Recording-level exploratory bootstrap, preserving each dataset's shared-fix count."""
    groups = defaultdict(list)
    for a, b in sorted(shared, key=lambda pair: pair[0]["case"]):
        groups[a["dataset"]].append(b["error_km"] - a["error_km"])
    if sum(map(len, groups.values())) < 2:
        return None, None
    rng = np.random.default_rng(20261120)
    draws = [
        rng.choice(values, size=(10000, len(values)), replace=True) for values in groups.values()
    ]
    return tuple(map(float, np.quantile(np.median(np.column_stack(draws), axis=1), [0.025, 0.975])))


def summarize(rows):
    grouped = defaultdict(list)
    baseline = {(r["case"], r["method"], r["calibration"]): r for r in rows if r["mode"] == "stock"}
    for r in rows:
        for subset in ("all", r["dataset"]):
            grouped[subset, r["method"], r["mode"], r["calibration"]].append(r)
    metrics, paired = [], []
    for (subset, m, mode, arm), group in grouped.items():
        fixes = [r for r in group if r["error_km"] is not None]
        errors = [r["error_km"] for r in fixes]
        labels = dict(dataset=subset, method=m, mode=mode, calibration=arm)
        metrics.append(
            dict(
                **labels,
                assigned=len(group),
                fixes=len(fixes),
                within_1km=sum(e <= 1 for e in errors),
                within_2km=sum(e <= 2 for e in errors),
                median_km=median(errors),
                p95_km=float(np.quantile(errors, 0.95)) if errors else None,
                median_rf_rms_hz=median([r["rf_rms_hz"] for r in fixes]),
            )
        )
        for reference in dict.fromkeys(["original", m]):
            pairs = [(baseline[r["case"], reference, arm], r) for r in group]
            shared = [
                (a, b) for a, b in pairs if a["error_km"] is not None and b["error_km"] is not None
            ]
            delta = [b["error_km"] - a["error_km"] for a, b in shared]
            low, high = paired_interval(shared)
            paired.append(
                dict(
                    **labels,
                    reference=reference,
                    both=len(shared),
                    gained=sum(
                        a["error_km"] is None and b["error_km"] is not None for a, b in pairs
                    ),
                    lost=sum(a["error_km"] is not None and b["error_km"] is None for a, b in pairs),
                    closer=sum(x < 0 for x in delta),
                    farther=sum(x > 0 for x in delta),
                    median_before_km=median([a["error_km"] for a, b in shared]),
                    median_after_km=median([b["error_km"] for a, b in shared]),
                    median_delta_km=median(delta),
                    delta_bootstrap_low_km=low,
                    delta_bootstrap_high_km=high,
                    median_delta_rf_rms_hz=median(
                        [b["rf_rms_hz"] - a["rf_rms_hz"] for a, b in shared]
                    ),
                )
            )
    return metrics, paired


def local_costs(cases):
    rows = []
    for c in cases:
        r = read(WORK / c["id"] / "local-measurements.json")
        for m, obs in r["rows"].items():
            delta = np.array([v[4] - v[3] for v in obs])
            rows.append(
                dict(
                    case=c["id"],
                    method=m,
                    admitted=len(obs),
                    interior=sum(v[5] for v in obs),
                    median_absolute_change_hz=float(np.median(abs(delta))),
                    p95_absolute_change_hz=float(np.quantile(abs(delta), 0.95)),
                    two_method_unique_calls=r["calls"],
                    shared_replay_cpu_s=r["cpu_s"],
                    shared_replay_wall_s=r["raw_wall_s"],
                )
            )
    return rows


def run(include_traces=True):
    cases = [r["case"] for r in read(panel.OUT / "roster.json")["cases"]]
    predictions = inventory(cases, include_traces)
    rows = score_rows(cases, predictions)
    summary, paired = summarize(rows)
    for filename, content in [
        ("recordings.csv", rows),
        ("summary.csv", summary),
        ("paired.csv", paired),
        ("local-cost.csv", local_costs(cases)),
    ]:
        write_csv(OUT / filename, content)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--positions-only",
        action="store_true",
        help="Score sealed endpoints while publication traces are replaying",
    )
    run(not parser.parse_args().positions_only)
