"""Visit-cached, bounded continuous GLRT census of both-sign stable matches."""

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


def census_rows(rows):
    return sorted((row for row in rows if row["stable_confident_match"] == "True"),
                  key=lambda row: int(row["row"]))


def local_peak(scores):
    values = np.asarray(scores, dtype=float)
    if values.shape != (21,) or np.any(~np.isfinite(values)):
        raise ValueError("local peak requires 21 finite scores")
    winner = int(np.argmax(values))
    offset = -250. + 25. * winner
    edge = winner in (0, 20)
    interpolated = False
    if not edge:
        left, center, right = values[winner - 1:winner + 2]
        curvature = left - 2 * center + right
        if curvature < 0:
            displacement = .5 * (left - right) / curvature
            if abs(displacement) <= 1:
                offset += 25. * float(displacement)
                interpolated = True
    return offset, edge, interpolated


def summarize(records):
    groups = defaultdict(list)
    for row in records:
        sign = ("improved" if float(row["path_attributed_data_gain"]) > 0 else
                "worsened" if float(row["path_attributed_data_gain"]) < 0 else "unchanged")
        for key in ((row["session"], "all", "all", "all"),
                    (row["session"], row["truth_satellite"], row["receiver"], sign)):
            groups[key].append(row)
    results = []
    for key, rows in sorted(groups.items(), key=lambda item: str(item[0])):
        valid = [row for row in rows if row["status"] == "available"]
        changes = np.asarray([row["exact_score_change"] for row in valid], dtype=float)
        proxy = np.asarray([float(row["path_attributed_data_gain"]) for row in valid])
        results.append({
            "session": key[0], "satellite": key[1], "receiver": key[2], "proxy_class": key[3],
            "eligible_count": len(rows), "available_count": len(valid),
            "status_counts": {status: sum(row["status"] == status for row in rows)
                              for status in sorted({row["status"] for row in rows})},
            "south_score_positive_count": int(np.sum(changes > 0)),
            "south_score_negative_count": int(np.sum(changes < 0)),
            "score_proxy_sign_agreement_count": int(np.sum(np.sign(changes) == np.sign(proxy))),
            "sum_exact_score_change": float(changes.sum()),
            "sum_control_score_change": float(sum(row["control_score_change"] for row in valid)),
            "sum_proxy_gain_available": float(proxy.sum()),
            "maximum_score_replay_error": max((row["score_parity_error"] for row in valid),
                                               default=None),
        })
    return results


def worker(session, partition, deadline):
    from edge_alias_diagnostic import _metadata
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    from leo.analysis.starlink import pilot_methods

    started = time.monotonic()
    directory = ROOT / "south-point-attribution" / f"{session}-pruned"
    with (directory / "all-points.csv").open() as stream:
        rows = census_rows(list(csv.DictReader(stream)))
    manifest = json.loads((ROOT / "scans" / session / "bundle.json").read_text())
    provenance = manifest["provenance"]
    _, _, metadata, _, rate = _metadata(
        Path("/srv/bulk/leo"), session, provenance["input_manifest_sha256"],
        provenance["analysis_manifest_sha256"],
    )
    metadata_s = time.monotonic() - started
    visits = defaultdict(list)
    records = []
    for row in rows:
        point = metadata[int(row["original_row"])]
        if point is None:
            if int(row["row"]) % 2 == partition:
                records.append({**row, "session": session, "status": "missing_metadata"})
            continue
        if point["probe_key"][0] % 2 == partition:
            visits[point["probe_key"][0]].append((row, point))
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    read_s = compute_s = 0.0
    read_bytes = read_count = 0
    try:
        published = store.inspect(session)
        if published.manifest_sha256 != provenance["input_manifest_sha256"]:
            raise ValueError("IQ manifest differs from frozen observations")
        receivers = list(published.manifest.receipt.plan.geometry.receiver_ids)
        with store.reader(session, expected=published) as reader:
            for visit_index, members in sorted(visits.items()):
                raw = None
                cache = {}
                visit_error = None
                if time.monotonic() < deadline:
                    begin = time.monotonic()
                    try:
                        visit, raw = reader.read_visit_ci16(visit_index)
                        read_bytes += raw.nbytes
                        read_count += 1
                    except Exception as error:
                        visit_error = f"{type(error).__name__}: {error}"
                    read_s += time.monotonic() - begin
                for row, point in members:
                    _, receiver, probe_index = point["probe_key"]
                    record = {**row, "session": session, "visit_index": visit_index,
                              "probe_index": probe_index, "candidate_rank": point["candidate_rank"],
                              "integer_epoch_sample": point["integer_epoch_sample"],
                              "fractional_epoch_offset_samples":
                                  point["fractional_epoch_offset_samples"],
                              "acquired_cfo_hz": point["acquired_cfo_hz"],
                              "native_residual_hz": point["native_residual_cfo_hz"],
                              "status": "budget_skipped", "sample_rate_hz": rate}
                    if visit_error:
                        record.update(status="read_error", error=visit_error)
                    elif time.monotonic() < deadline and raw is not None:
                        begin = time.monotonic()
                        try:
                            measured = float(row["measured_hz"])
                            if abs(measured - point["tracking_cfo_hz"]) > 1e-6:
                                raise ValueError("persisted CFO and original row differ")
                            key = (receiver, probe_index)
                            if key not in cache:
                                start = probe_index * (120 * rate // 1000)
                                segment = raw[start:start + 20 * rate // 1000,
                                              receivers.index(receiver)]
                                if len(segment) != 20 * rate // 1000:
                                    raise ValueError("incomplete 20ms probe")
                                sample_hash = hashlib.sha256(
                                    np.ascontiguousarray(segment).tobytes()).hexdigest()
                                samples = (segment[:, 0].astype(float)
                                           + 1j * segment[:, 1].astype(float))
                                cache[key] = samples, sample_hash
                            samples, sample_hash = cache[key]
                            workspace = pilot_methods._conditioned_correlation_workspace(
                                samples, rate, point["integer_epoch_sample"],
                                point["acquired_cfo_hz"], edge=visit.event.target.edge,
                                selected_symbols=np.arange(2, 66),
                                fractional_epoch_offset_samples=
                                    point["fractional_epoch_offset_samples"],
                            )
                            exact = workspace.select(np.arange(2, 66))
                            control = workspace.select(np.arange(2, 66), control=True)
                            replay, replay_control = pilot_methods._glrt_pair(
                                exact, control, size=512)
                            spec = point["candidate_spec"]
                            parity_error = max(
                                abs(replay[0] - spec["fractional_exact_score"]),
                                abs(replay_control[0] - spec["fractional_control_score"]))
                            residual_error = abs(closest_alias(
                                replay[1], point["native_residual_cfo_hz"])
                                - point["native_residual_cfo_hz"])
                            queries = np.array([
                                measured,
                                closest_alias(measured - float(row["truth_residual_hz"]), measured),
                                closest_alias(measured - float(
                                    row["south_residual_same_satellite_hz"]), measured),
                            ])
                            queries = np.r_[queries, measured + np.arange(-250., 251., 25.)]
                            frequencies = queries - point["acquired_cfo_hz"]
                            scores = continuous_scores(
                                exact.values, exact.times_s[0] - exact.times_s[0, 0], frequencies)
                            controls = continuous_scores(
                                control.values, control.times_s[0] - control.times_s[0, 0],
                                frequencies)
                            peak_offset, peak_edge, interpolated = local_peak(scores[3:])
                            parity = parity_error <= 1e-6 and residual_error <= 1e-6
                            record.update(
                                status="available" if parity else "parity_failed",
                                probe_ci16_sha256=sample_hash, score_parity_error=parity_error,
                                native_residual_parity_error_hz=residual_error,
                                replay_exact_score=replay[0],
                                replay_control_score=replay_control[0],
                                stored_exact_score=spec["fractional_exact_score"],
                                stored_control_score=spec["fractional_control_score"],
                                exact_score_change=float(scores[2] - scores[1]),
                                control_score_change=float(controls[2] - controls[1]),
                                refined_cfo_offset_hz=peak_offset, local_peak_edge=peak_edge,
                                local_peak_parabolic_interpolation=interpolated,
                            )
                            for index, label in enumerate(("measured", "truth", "south")):
                                record[f"{label}_frequency_hz"] = float(queries[index])
                                record[f"{label}_exact_score"] = float(scores[index])
                                record[f"{label}_control_score"] = float(controls[index])
                        except Exception as error:
                            record.update(status="replay_error",
                                          error=f"{type(error).__name__}: {error}")
                        compute_s += time.monotonic() - begin
                    records.append(record)
    finally:
        store.close()
    return records, {"session": session, "partition": partition, "metadata_s": metadata_s,
                     "iq_read_s": read_s, "score_compute_s": compute_s,
                     "visit_read_count": read_count, "visit_bytes_read": read_bytes,
                     "elapsed_s": time.monotonic() - started}


def run():
    from edge_alias_diagnostic import _metadata
    from leo.storage.adaptive_hop import AdaptiveHopIqStore

    from leo.analysis.starlink import pilot_methods

    output = ROOT / "south-glrt-surface-census"
    output.mkdir(exist_ok=False)
    paths = [Path(__file__), ROOT / "south_glrt_surface_probe.py",
             Path(inspect.getfile(pilot_methods)), Path(inspect.getfile(_metadata)),
             Path(inspect.getfile(AdaptiveHopIqStore))]
    expected = {}
    for session in SESSIONS:
        directory = ROOT / "south-point-attribution" / f"{session}-pruned"
        paths.extend(directory / name
                     for name in ("all-points.csv", "summary.json", "evidence.npz"))
        paths.append(ROOT / "scans" / session / "bundle.json")
        with (directory / "all-points.csv").open() as stream:
            expected[session] = census_rows(list(csv.DictReader(stream)))
    hashes = {str(path.resolve()): digest(path) for path in paths}
    started = time.monotonic()
    deadline = started + 170.0
    records, clocks, failures = [], [], []
    with ProcessPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(worker, session, partition, deadline): (session, partition)
                   for session in SESSIONS for partition in (0, 1)}
        for future in as_completed(futures):
            try:
                rows, clock = future.result()
                records.extend(rows)
                clocks.append(clock)
                print(json.dumps(clock | {"returned_rows": len(rows)}), flush=True)
            except Exception as error:
                failures.append({"task": futures[future],
                                 "error": f"{type(error).__name__}: {error}"})
    seen = {(row["session"], row["row"]) for row in records}
    if len(seen) != len(records):
        raise ValueError("duplicate census rows")
    for session, rows in expected.items():
        records.extend({**row, "session": session, "status": "worker_failed"}
                       for row in rows if (session, row["row"]) not in seen)
    records.sort(key=lambda row: (row["session"], int(row["row"])))
    if any(digest(path) != value for path, value in hashes.items()):
        raise ValueError("source changed during census")
    fields = list(dict.fromkeys(key for row in records for key in row))
    with (output / "all-stable-points.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    receipt = {
        "schema": "ds13-south-glrt-surface-census/v1", "source_hashes": hashes,
        "output_csv_sha256": digest(output / "all-stable-points.csv"),
        "eligible_counts": {session: len(rows) for session, rows in expected.items()},
        "complete": all(row["status"] == "available" for row in records),
        "wall_elapsed_s": time.monotonic() - started, "wall_budget_s": 180,
        "new_work_deadline_s": 170, "workers": 4, "threads_per_worker": 1,
        "worker_clocks": clocks, "worker_failures": failures, "aggregates": summarize(records),
        "order": "Session split by visit_index modulo 2; ascending visits then original CSV row. "
                 "One visit and its probes cached per worker. Both proxy-gain signs retained.",
        "local_peak": "Summary CFO +/-250Hz, step25Hz; three-point parabolic interpolation "
                      "at interior maxima, edge maxima flagged. Fixed epoch and demodulation.",
        "scope": "Census of stable_confident_match=True peaks only, not all observed peaks. "
                 "Frozen acquired CFO and fractional epoch, continuous symbol-lag response at "
                 "measured/truth/south CFOs. Native512 exact/control and residual replay gates. "
                 "Normalized score sums are descriptive, not a joint likelihood or geographic "
                 "confidence. Control changes use the same queried frequencies, not maximization. "
                 "No epoch or nuisance reoptimization. Budget/error rows remain in the CSV.",
    }
    with (output / "summary.json").open("x") as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False)
    print(json.dumps({"complete": receipt["complete"], "elapsed_s": receipt["wall_elapsed_s"],
                      "eligible": receipt["eligible_counts"]}), flush=True)


if __name__ == "__main__":
    run()
