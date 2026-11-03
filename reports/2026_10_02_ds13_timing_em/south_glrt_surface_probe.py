"""Small saved-IQ continuous residual-frequency audit at frozen GLRT epochs."""

from __future__ import annotations

import csv
import hashlib
import inspect
import json
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent
SESSIONS = {
    "scan-fw-911c4e5db9243281": (64013, 58484),
    "scan-fw-ffa1cc19d8d7c09f": (65745, 62739),
}
ALIAS_HZ = 1 / 4.4e-6


def closest_alias(frequency, anchor):
    return anchor + (frequency - anchor + ALIAS_HZ / 2) % ALIAS_HZ - ALIAS_HZ / 2


def continuous_scores(values, lags_s, frequencies):
    values = np.asarray(values, dtype=complex)
    lags = np.asarray(lags_s, dtype=float)
    frequencies = np.asarray(frequencies, dtype=float)
    if values.ndim != 2 or lags.shape != (values.shape[1],) or frequencies.ndim != 1:
        raise ValueError("correlations, symbol lags and frequencies must align")
    ceiling = float(np.sum(np.sum(np.abs(values), axis=1) ** 2))
    phase = np.exp(-2j * np.pi * frequencies[:, None] * lags[None, :])
    power = np.sum(np.abs(phase @ values.T) ** 2, axis=1)
    return power / ceiling if ceiling > 0 else power


def select_rows(rows, numbers, per_satellite=2):
    selected = []
    for number in numbers:
        eligible = [row for row in rows if row["stable_confident_match"] == "True"
                    and int(row["truth_satellite"]) == number
                    and float(row["path_attributed_data_gain"]) > 0]
        eligible.sort(key=lambda row: (-float(row["path_attributed_data_gain"]), int(row["row"])))
        groups = set()
        for row in eligible:
            if row["group"] in groups:
                continue
            selected.append(row)
            groups.add(row["group"])
            if len(groups) == per_satellite:
                break
    return selected


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run():
    from edge_alias_diagnostic import _metadata
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    from leo.analysis.starlink import pilot_methods

    output = ROOT / "south-glrt-surface-probe"
    output.mkdir(exist_ok=False)
    paths = [Path(__file__), Path(inspect.getfile(pilot_methods)),
             Path(inspect.getfile(_metadata)), Path(inspect.getfile(AdaptiveHopIqStore))]
    for session in SESSIONS:
        paths.extend([ROOT / "scans" / session / "bundle.json",
                      ROOT / "south-point-attribution" / f"{session}-pruned" / "all-points.csv",
                      ROOT / "south-point-attribution" / f"{session}-pruned" / "summary.json"])
    hashes = {str(path.resolve()): digest(path) for path in paths}
    records = []
    compute_s = 0.0
    started = time.monotonic()
    for session, numbers in SESSIONS.items():
        manifest = json.loads((ROOT / "scans" / session / "bundle.json").read_text())
        csv_path = ROOT / "south-point-attribution" / f"{session}-pruned" / "all-points.csv"
        with csv_path.open() as stream:
            chosen = select_rows(list(csv.DictReader(stream)), numbers)
        provenance = manifest["provenance"]
        _, _, metadata, _, rate = _metadata(
            Path("/srv/bulk/leo"), session, provenance["input_manifest_sha256"],
            provenance["analysis_manifest_sha256"],
        )
        store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
        try:
            published = store.inspect(session)
            if published.manifest_sha256 != provenance["input_manifest_sha256"]:
                raise ValueError("IQ manifest changed")
            with store.reader(session, expected=published) as reader:
                for row in chosen:
                    if compute_s >= 120 or time.monotonic() - started >= 540:
                        break
                    point = metadata[int(row["original_row"])]
                    if point is None:
                        raise ValueError("selected row has no exact GLRT metadata join")
                    if abs(float(row["measured_hz"]) - point["tracking_cfo_hz"]) > 1e-6:
                        raise ValueError("selected summary CFO differs from persisted candidate")
                    visit_index, receiver, probe_index = point["probe_key"]
                    begin = time.monotonic()
                    visit, raw = reader.read_visit_ci16(visit_index)
                    receivers = list(published.manifest.receipt.plan.geometry.receiver_ids)
                    column = receivers.index(receiver)
                    start = int(probe_index * .120 * rate)
                    stop = start + int(.020 * rate)
                    segment = raw[start:stop, column]
                    if len(segment) != int(.020 * rate):
                        raise ValueError("incomplete saved 20ms probe")
                    sample_bytes = np.ascontiguousarray(segment).tobytes()
                    sample_hash = hashlib.sha256(sample_bytes).hexdigest()
                    samples = segment[:, 0].astype(float) + 1j * segment[:, 1].astype(float)
                    workspace = pilot_methods._conditioned_correlation_workspace(
                        samples, rate, point["integer_epoch_sample"], point["acquired_cfo_hz"],
                        edge=visit.event.target.edge, selected_symbols=np.arange(2, 66),
                        fractional_epoch_offset_samples=point["fractional_epoch_offset_samples"],
                    )
                    exact = workspace.select(np.arange(2, 66))
                    control = workspace.select(np.arange(2, 66), control=True)
                    replay, replay_control = pilot_methods._glrt_pair(exact, control, size=512)
                    spec = point["candidate_spec"]
                    score_error = replay[0] - spec["fractional_exact_score"]
                    control_error = replay_control[0] - spec["fractional_control_score"]
                    parity = max(abs(score_error), abs(control_error)) <= 1e-6
                    measured = float(row["measured_hz"])
                    truth = closest_alias(measured - float(row["truth_residual_hz"]), measured)
                    south = closest_alias(
                        measured - float(row["south_residual_same_satellite_hz"]), measured,
                    )
                    grid = np.arange(-1000., 1000.1, 5.) + measured
                    queries = np.r_[measured, truth, south, grid]
                    residual = queries - point["acquired_cfo_hz"]
                    scores = continuous_scores(exact.values, exact.times_s[0] - exact.times_s[0, 0],
                                               residual)
                    control_scores = continuous_scores(
                        control.values, control.times_s[0] - control.times_s[0, 0], residual,
                    )
                    compute_s += time.monotonic() - begin
                    records.append({
                        "session": session, "selected_row": row, "metadata": point,
                        "sample_rate_hz": rate, "visit_index": visit_index,
                        "probe_start_in_visit_samples": start, "probe_sample_count": len(samples),
                        "probe_ci16_sha256": sample_hash, "replay_exact_score": replay[0],
                        "replay_control_score": replay_control[0], "replay_residual_hz": replay[1],
                        "stored_exact_score_difference": score_error,
                        "stored_control_score_difference": control_error, "replay_parity": parity,
                        "measured_truth_south_frequency_hz": queries[:3].tolist(),
                        "measured_truth_south_exact_score": scores[:3].tolist(),
                        "measured_truth_south_control_score": control_scores[:3].tolist(),
                        "south_minus_truth_exact_score": float(scores[2] - scores[1]),
                        "local_grid_best_offset_from_summary_hz": float(
                            grid[np.argmax(scores[3:])] - measured),
                        "local_grid_offset_hz": (grid - measured).tolist(),
                        "local_grid_exact_score": scores[3:].tolist(),
                        "comparison_available": parity,
                    })
                    print(json.dumps({"session": session, "row": row["row"], "parity": parity,
                                      "score_change": float(scores[2] - scores[1]),
                                      "compute_s": compute_s}), flush=True)
        finally:
            store.close()
    if any(digest(path) != expected for path, expected in hashes.items()):
        raise ValueError("source changed during surface audit")
    receipt = {
        "schema": "ds13-south-glrt-surface-probe/v1", "source_hashes": hashes,
        "actual_iq_compute_and_read_s": compute_s, "elapsed_s": time.monotonic() - started,
        "records": records, "complete": len(records) == 8,
        "scope": "Targeted favored stable rows: two distinct groups per named satellite. "
                 "Fixed acquired demodulation and fractional epoch; continuous symbol-lag "
                 "phase frequency replaces the native 512-bin residual grid. Exact/control "
                 "scores are normalized correlation statistics, not localization likelihoods. "
                 "No epoch reoptimization or all-row inference. Stored replay parity is required. "
                 "Truth/south curves use the attribution's compensated group-median geometry.",
    }
    with (output / "receipt.json").open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    run()
