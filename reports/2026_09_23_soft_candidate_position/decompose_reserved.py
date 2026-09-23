"""Decompose frozen soft posterior predictive squared error after inference."""

import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
spec = importlib.util.spec_from_file_location(
    "runner", REPO / "tools/research/position_soft_candidate.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
joint = runner.load(REPO / "tools/research/sixteen_joint_compare.py", "joint")
statistics = runner.load(REPO / "tools/research/position_soft_statistics.py", "statistics")
cache_helper = runner.load(REPO / "tools/research/position_regularized_search.py", "cache_helper")
caches, _, _ = cache_helper._cache_index(
    REPO / "reports/2026_09_23_day_position_validation/replication"
)
source = HERE / "results.json"
data = json.loads(source.read_text())
rows = []
for window in data["windows"]:
    selected = next(a for a in window["arms"] if a["method"] == "soft")["selected"]
    point = selected["latitude_deg"], selected["longitude_deg"]
    total_weight = signal_sum = null_sum = 0.0
    for sid in window["session_ids"]:
        assert (
            runner.digest(caches[sid] / "evidence" / f"{sid}.json")
            == data["input_bindings"][sid]["evidence"]
        )
        assert (
            runner.digest(caches[sid] / "scans" / f"{sid}.npz")
            == data["input_bindings"][sid]["states"]
        )
        evidence, arrays = joint.load_scan_cache(caches[sid], sid)
        for track in evidence["tracks"]:
            p = joint.prediction_for_track(evidence, arrays, track, *point)
            stats = statistics.track_statistics(p, include_evaluation=True)
            train = np.asarray(p.training_mask, bool)
            y = np.asarray(p.measured_hz)
            null_mse = np.mean((y[~train] - y[train].mean()) ** 2)
            weight = len(np.unique(np.floor(p.times_s)))
            contribution = stats["null_probability"] * null_mse
            null_sum += weight * contribution
            signal_sum += weight * (stats["soft_reserved_mse_hz2"] - contribution)
            total_weight += weight
    expected = np.sqrt((signal_sum + null_sum) / total_weight)
    assert np.isclose(expected, selected["native_frozen_posterior_reserved_rmse_hz"])
    rows.append(
        {
            "window_id": window["window_id"],
            "posterior_expected_rmse_hz": expected,
            "null_fraction_of_squared_error": null_sum / (signal_sum + null_sum),
            "signal_contribution_rmse_hz": np.sqrt(signal_sum / total_weight),
        }
    )
(HERE / "reserved_decomposition.json").write_text(
    json.dumps(
        {
            "source_sha256": runner.digest(source),
            "worker_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "rows": rows,
        },
        indent=2,
    )
    + "\n"
)
