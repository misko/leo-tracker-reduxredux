"""Saved-IQ orbit-window peak refinement, with an orbit-independent local control."""

from __future__ import annotations

import csv
import hashlib
import inspect
import json
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
from south_glrt_surface_probe import ROOT, SESSIONS, closest_alias, continuous_scores, digest

CENSUS = ROOT / "south-glrt-surface-census"
OUTPUT = ROOT / "south-orbit-glrt-refinement"
GUIDED_OFFSETS = np.arange(-200., 201., 10.)
CONTROL_OFFSETS = np.arange(-1000., 1001., 10.)


def peak_frequency(frequencies, scores):
    frequencies = np.asarray(frequencies, dtype=float)
    scores = np.asarray(scores, dtype=float)
    if (frequencies.ndim != 1 or len(frequencies) < 3 or scores.shape != frequencies.shape
            or np.any(~np.isfinite(scores)) or np.any(np.diff(frequencies) <= 0)):
        raise ValueError("peak requires aligned finite scores and increasing frequencies")
    winner = int(np.argmax(scores))
    edge = winner in (0, len(scores) - 1)
    frequency = float(frequencies[winner])
    if not edge:
        left, center, right = scores[winner - 1:winner + 2]
        curvature = left - 2 * center + right
        if curvature < 0:
            step = frequencies[winner + 1] - frequencies[winner]
            shift = .5 * (left - right) / curvature
            if abs(shift) <= 1:
                frequency += float(step * shift)
    return frequency, edge, winner


def refine_correlations(exact, control, acquired, measured, truth, south):
    centers = {"control": measured, "truth": truth, "south": south}
    grids = {name: center + (CONTROL_OFFSETS if name == "control" else GUIDED_OFFSETS)
             for name, center in centers.items()}
    exact_lags = exact.times_s[0] - exact.times_s[0, 0]
    control_lags = control.times_s[0] - control.times_s[0, 0]
    result, surfaces = {}, {}
    before = continuous_scores(exact.values, exact_lags, np.array([measured]) - acquired)[0]
    result["measured_replayed_exact_score"] = float(before)
    for name, grid in grids.items():
        scores = continuous_scores(exact.values, exact_lags, grid - acquired)
        controls = continuous_scores(control.values, control_lags, grid - acquired)
        frequency, edge, winner = peak_frequency(grid, scores)
        value = float(continuous_scores(exact.values, exact_lags,
                                       np.array([frequency - acquired]))[0])
        if value < scores[winner]:
            frequency, value = float(grid[winner]), float(scores[winner])
        control_value = float(continuous_scores(control.values, control_lags,
                                               np.array([frequency - acquired]))[0])
        result.update({f"{name}_refined_frequency_hz": frequency,
                       f"{name}_boundary_hit": edge,
                       f"{name}_refined_exact_score": value,
                       f"{name}_refined_control_score": control_value,
                       f"{name}_score_gain_from_summary": value - before,
                       f"{name}_residual_to_truth_hz": frequency - truth,
                       f"{name}_residual_to_south_hz": frequency - south})
        surfaces[f"{name}_exact"] = scores
        surfaces[f"{name}_control"] = controls
        if name != "control":
            for radius in (50, 100):
                inside = np.abs(GUIDED_OFFSETS) <= radius
                limited, boundary, _ = peak_frequency(grid[inside], scores[inside])
                score = float(continuous_scores(
                    exact.values, exact_lags, np.array([limited - acquired]))[0])
                result.update({f"{name}{radius}_refined_frequency_hz": limited,
                               f"{name}{radius}_boundary_hit": boundary,
                               f"{name}{radius}_score_gain_from_summary": score - before})
    result["guided_south_minus_truth_peak_score"] = (
        result["south_refined_exact_score"] - result["truth_refined_exact_score"])
    return result, surfaces


def worker(session, partition, deadline):
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    from leo.analysis.starlink import pilot_methods

    started = time.monotonic()
    with (CENSUS / "all-stable-points.csv").open() as stream:
        rows = [row for row in csv.DictReader(stream) if row["session"] == session
                and int(row["visit_index"]) % 2 == partition]
    visits = defaultdict(list)
    for row in rows:
        visits[int(row["visit_index"])].append(row)
    manifest = json.loads((ROOT / "scans" / session / "bundle.json").read_text())
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    records, grids = [], []
    read_s = compute_s = 0.
    try:
        published = store.inspect(session)
        if published.manifest_sha256 != manifest["provenance"]["input_manifest_sha256"]:
            raise ValueError("saved IQ input manifest changed")
        receivers = list(published.manifest.receipt.plan.geometry.receiver_ids)
        with store.reader(session, expected=published) as reader:
            for visit_index, members in sorted(visits.items()):
                raw, read_error = None, None
                cache = {}
                if time.monotonic() < deadline:
                    begin = time.monotonic()
                    try:
                        visit, raw = reader.read_visit_ci16(visit_index)
                    except Exception as error:
                        read_error = str(error)
                    read_s += time.monotonic() - begin
                for row in members:
                    result = dict(row, status="budget_skipped")
                    if read_error:
                        result.update(status="read_error", error=read_error)
                    elif raw is not None and time.monotonic() < deadline:
                        begin = time.monotonic()
                        try:
                            rate = int(row["sample_rate_hz"])
                            key = (int(row["receiver"]), int(row["probe_index"]))
                            if key not in cache:
                                start = key[1] * (120 * rate // 1000)
                                segment = raw[start:start + 20 * rate // 1000,
                                              receivers.index(key[0])]
                                sample_hash = hashlib.sha256(
                                    np.ascontiguousarray(segment).tobytes()).hexdigest()
                                samples = (segment[:, 0].astype(float)
                                           + 1j * segment[:, 1].astype(float))
                                cache[key] = samples, sample_hash
                            samples, sample_hash = cache[key]
                            if sample_hash != row["probe_ci16_sha256"]:
                                raise ValueError("probe bytes differ from sealed census")
                            acquired = float(row["acquired_cfo_hz"])
                            workspace = pilot_methods._conditioned_correlation_workspace(
                                samples, rate, int(row["integer_epoch_sample"]), acquired,
                                edge=visit.event.target.edge, selected_symbols=np.arange(2, 66),
                                fractional_epoch_offset_samples=float(
                                    row["fractional_epoch_offset_samples"]),
                            )
                            exact = workspace.select(np.arange(2, 66))
                            control = workspace.select(np.arange(2, 66), control=True)
                            replay, replay_control = pilot_methods._glrt_pair(
                                exact, control, size=512)
                            score_error = max(
                                abs(replay[0] - float(row["stored_exact_score"])),
                                abs(replay_control[0] - float(row["stored_control_score"])))
                            residual_error = abs(closest_alias(
                                replay[1], float(row["native_residual_hz"]))
                                - float(row["native_residual_hz"]))
                            if score_error > 1e-6 or residual_error > 1e-6:
                                raise ValueError("native512 replay parity failed")
                            refined, surfaces = refine_correlations(
                                exact, control, acquired, float(row["measured_hz"]),
                                float(row["truth_frequency_hz"]), float(row["south_frequency_hz"]),
                            )
                            result.update(refined, status="available",
                                          native512_score_parity_error=score_error,
                                          native512_residual_parity_error_hz=residual_error)
                            grids.append({"session": session, "row": int(row["row"]), **surfaces})
                        except Exception as error:
                            result.update(status="error", error=f"{type(error).__name__}: {error}")
                        compute_s += time.monotonic() - begin
                    records.append(result)
    finally:
        store.close()
    return records, grids, {"session": session, "partition": partition,
                            "elapsed_s": time.monotonic() - started,
                            "iq_read_s": read_s, "compute_s": compute_s}


def aggregate(rows):
    valid = [row for row in rows if row["status"] == "available"]
    summary = {"eligible": len(rows), "available": len(valid), "methods": {}}
    for method in ("summary", "control", "truth", "south",
                   "truth50", "south50", "truth100", "south100"):
        frequency = np.array([float(row["measured_hz"] if method == "summary"
                                    else row[f"{method}_refined_frequency_hz"]) for row in valid])
        stats = {}
        for hypothesis in ("truth", "south"):
            target = np.array([float(row[f"{hypothesis}_frequency_hz"]) for row in valid])
            stats[f"rms_to_{hypothesis}_hz"] = float(np.sqrt(np.mean((frequency - target) ** 2)))
        if method != "summary":
            stats["boundary_hits"] = sum(row[f"{method}_boundary_hit"] for row in valid)
            stats["sum_score_gain_from_summary"] = sum(
                row[f"{method}_score_gain_from_summary"] for row in valid)
        summary["methods"][method] = stats
    summary["sum_fixed_south_minus_truth_score"] = sum(float(row["exact_score_change"])
                                                       for row in valid)
    summary["sum_guided_south_minus_truth_peak_score"] = sum(
        row["guided_south_minus_truth_peak_score"] for row in valid)
    return summary


def plot_results(records, summaries):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(2, 2, figsize=(13, 8), sharey=True)
    panels = [(list(SESSIONS)[0], 64013), (list(SESSIONS)[0], 58484),
              (list(SESSIONS)[1], 65745), (list(SESSIONS)[1], 62739)]
    for axis, (session, number) in zip(axes.flat, panels, strict=True):
        rows = sorted([row for row in records if row["session"] == session
                       and int(row["truth_satellite"]) == number
                       and row["status"] == "available"], key=lambda row: float(row["time_s"]))
        times = [float(row["time_s"]) for row in rows]
        for method, label, color in (("summary", "Stored CFO", "#777777"),
                                     ("control", "Independent local peak", "#2369bd"),
                                     ("truth", "Truth-guided ±200Hz", "#dc7028")):
            residual = [float(row["measured_hz"] if method == "summary"
                              else row[f"{method}_refined_frequency_hz"])
                        - float(row["truth_frequency_hz"]) for row in rows]
            axis.scatter(times, residual, s=10, alpha=.55, label=label, color=color)
        axis.axhline(0, color="black", linewidth=.6)
        axis.axhline(200, color="#dc7028", linestyle=":", linewidth=.7)
        axis.axhline(-200, color="#dc7028", linestyle=":", linewidth=.7)
        axis.set_title(f"{'A' if session == list(SESSIONS)[0] else 'B'} — satellite {number}")
        axis.set_xlabel("Receive time (s)")
        axis.set_ylabel("CFO minus compensated truth curve (Hz)")
    axes[0, 0].legend(fontsize=8)
    footer = []
    for label, session in zip(("A", "B"), SESSIONS, strict=True):
        summary = summaries[session]
        methods = summary["methods"]
        footer.append(
            f"{label}: n={summary['available']}; truth RMS stored/control/guided200 = "
            f"{methods['summary']['rms_to_truth_hz']:.1f}/"
            f"{methods['control']['rms_to_truth_hz']:.1f}/"
            f"{methods['truth']['rms_to_truth_hz']:.1f} Hz; "
            f"guided boundary {methods['truth']['boundary_hits']}/{summary['available']}")
    figure.suptitle("Saved-IQ continuous GLRT refinement at fixed original identities and epochs")
    figure.text(.5, .055, "\n".join(footer), ha="center", fontsize=10)
    figure.text(.5, .012, "Original-posterior selection; RMS comparison is selection-conditioned. "
                "Oracle-guided windows enforce proximity; no location-accuracy inference.",
                ha="center", fontsize=9)
    figure.tight_layout(rect=(0, .115, 1, .95))
    for suffix in ("png", "svg"):
        figure.savefig(OUTPUT / f"dominant-refinement.{suffix}", dpi=160)
    plt.close(figure)


def run():
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    from leo.analysis.starlink import pilot_methods

    OUTPUT.mkdir(exist_ok=False)
    census = json.loads((CENSUS / "summary.json").read_text())
    if digest(CENSUS / "all-stable-points.csv") != census["output_csv_sha256"]:
        raise ValueError("census CSV digest mismatch")
    paths = [Path(__file__), ROOT / "south_glrt_surface_probe.py", CENSUS / "summary.json",
             CENSUS / "all-stable-points.csv", Path(inspect.getfile(pilot_methods)),
             Path(inspect.getfile(AdaptiveHopIqStore))]
    hashes = dict(census["source_hashes"])
    for path in paths:
        resolved = str(path.resolve())
        value = digest(path)
        if resolved in hashes and hashes[resolved] != value:
            raise ValueError("census source dependency changed")
        hashes[resolved] = value
    if any(digest(path) != value for path, value in hashes.items()):
        raise ValueError("census source closure changed")
    started = time.monotonic()
    records, surfaces, clocks = [], [], []
    with ProcessPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(worker, session, partition, started + 165.)
                   for session in SESSIONS for partition in (0, 1)]
        for future in as_completed(futures):
            rows, grids, clock = future.result()
            records.extend(rows)
            surfaces.extend(grids)
            clocks.append(clock)
            print(json.dumps(clock | {"rows": len(rows)}), flush=True)
    records.sort(key=lambda row: (row["session"], int(row["row"])))
    surfaces.sort(key=lambda row: (row["session"], row["row"]))
    if any(digest(path) != value for path, value in hashes.items()):
        raise ValueError("source closure changed during replay")
    fields = list(dict.fromkeys(key for row in records for key in row))
    with (OUTPUT / "all-stable-points.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    arrays = {key: np.array([row[key] for row in surfaces])
              for key in ("session", "row", "truth_exact", "truth_control", "south_exact",
                          "south_control", "control_exact", "control_control")}
    arrays.update(guided_offsets_hz=GUIDED_OFFSETS, control_offsets_hz=CONTROL_OFFSETS)
    with (OUTPUT / "score-grids.npz").open("xb") as stream:
        np.savez_compressed(stream, **arrays)
    summaries = {session: aggregate([row for row in records if row["session"] == session])
                 for session in SESSIONS}
    numerical_elapsed = time.monotonic() - started
    plot_results(records, summaries)
    receipt = {
        "schema": "ds13-south-orbit-glrt-refinement/v1", "source_hashes": hashes,
        "wall_elapsed_s": time.monotonic() - started, "numerical_wall_s": numerical_elapsed,
        "wall_budget_s": 180.,
        "worker_clocks": clocks, "complete": all(row["status"] == "available" for row in records),
        "summaries": summaries,
        "artifacts": {name: digest(OUTPUT / name)
                      for name in ("all-stable-points.csv", "score-grids.npz",
                                   "dominant-refinement.png", "dominant-refinement.svg")},
        "scope": "Frozen stable confident membership. IQ bytes and native512 scores replayed. "
                 "Fixed epoch/acquired demodulation; continuous symbol-lag exact-score maxima. "
                 "Truth/south windows +/-200Hz step10; orbit-independent control is summary CFO "
                 "+/-1000Hz step10, not a global peak search. Interior parabolic estimates are "
                 "evaluated directly and retained only if no worse than the grid maximum. "
                 "Raw means are unweighted per peak; no position/nuisance/identity fits. "
                 "Guided RMS reduction is circular because the orbit defines the allowed window. "
                 "Stable cohort selected on ORIGINAL residuals/posteriors, so stored-vs-refined "
                 "RMS is selection-conditioned, not unbiased estimator quality. Known-site oracle "
                 "guidance with fixed original identities/epochs is not blind new detection. "
                 "Normalized scores and overlapping-window peak differences are not joint "
                 "likelihoods or geographic confidence. CSV records include skipped/error rows.",
        "grid_mapping": "session,row join CSV. Add guided offsets to truth/south_frequency_hz; "
                        "add control offsets to measured_hz. *_control uses control templates.",
    }
    with (OUTPUT / "summary.json").open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
    print(json.dumps({"complete": receipt["complete"], "wall_elapsed_s": receipt["wall_elapsed_s"],
                      "summaries": receipt["summaries"]}), flush=True)


if __name__ == "__main__":
    run()
