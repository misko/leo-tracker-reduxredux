#!/usr/bin/env python3
"""Exact donor replay and retained-target age binding; no geographic fitting."""
from __future__ import annotations

import hashlib
import inspect
import json
from pathlib import Path
import sys
import time

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
DONOR = ROOT / "reports/2026_09_29_donor_residual_transfer"
RECURRENCE = ROOT / "reports/2026_09_29_catalogue_recurrence/result.json"
TARGET_REPLAY = ROOT / "reports/2026_09_29_orbit_revision_prediction/results.json"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "reports/2026_09_29_orbit_revision_support"))
import ds7_fast_baseline_adapter as fast  # noqa: E402
from inventory import epoch_ns  # noqa: E402


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def element_digest(record):
    return hashlib.sha256((record.first_line + "\n" + record.second_line + "\n").encode()).hexdigest()


def prediction(pos, vel, receiver, weight):
    p = pos[0] * (1.0 - weight) + pos[1] * weight
    v = vel[0] * (1.0 - weight) + vel[1] * weight
    unit = p - receiver
    unit /= np.linalg.norm(unit, axis=-1)[:, None]
    return -fast.baseline.REFERENCE_RF_HZ / fast.baseline.LIGHT_KM_S * np.sum(unit * v, axis=-1)


def main():
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from leo.operations.tle_archive import TleArchiveReader
    from leo.sky.propagation import parse_element_set_records, parse_element_sets

    started = time.monotonic()
    plan_path = DONOR / "plan.json"
    plan = json.loads(plan_path.read_text())
    recurrence = json.loads(RECURRENCE.read_text())
    target_replay = json.loads(TARGET_REPLAY.read_text())
    if target_replay["max_baseline_difference"] != {
        "position_km": 0.0,
        "velocity_km_s": 0.0,
        "frequency_hz": 0.0,
    }:
        raise ValueError("existing target exact replay is not exact")
    target_rows = {
        (row["unit_id"], row["session_id"], row["track_id"], int(row["number"])): row
        for row in target_replay["rows"]
    }
    mapping = {
        (scan["session_id"], track["track_id"]): track["numbers"]
        for scan in recurrence["scans"]
        for track in scan["tracks"]
    }
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    refs = archive.list_snapshots()
    cache = {}

    def records(ref):
        key = str(ref.path)
        if key not in cache:
            parsed = parse_element_set_records(archive.read(ref))
            values = {item.satellite_number: item for item in parsed}
            if len(values) != len(parsed):
                raise ValueError("duplicate NORAD object in pinned snapshot")
            cache[key] = values
        return cache[key]

    output_rows = []
    maxima = np.zeros(3)
    hashes = {}
    donor_count = target_count = 0
    for unit in plan["units"]:
        dataset = unit["unit_id"][:3]
        case_path = DONOR / "runs" / unit["unit_id"] / "result.json"
        case_document = json.loads(case_path.read_text())
        hashes[str(case_path.relative_to(ROOT))] = digest(case_path)
        by_track = {(c["session_id"], c["track_id"]): c for c in case_document["cases"]}
        if len(by_track) != len(case_document["cases"]):
            raise ValueError("retained case identity is not unique")
        for input_index, entry in enumerate(unit["group"]["inputs"]):
            for artifact in entry["artifacts"]:
                path = Path(artifact["path"])
                observed = digest(path)
                if observed != artifact["sha256"].removeprefix("sha256:"):
                    raise ValueError("frozen artifact digest mismatch")
                hashes[str(path.relative_to(ROOT))] = observed
            manifest_path = Path(next(
                artifact["path"] for artifact in entry["artifacts"]
                if artifact["kind"] == "candidates" and artifact["path"].endswith(".json")
            ))
            manifest = json.loads(manifest_path.read_text())
            sources = []
            for source in manifest["provider_sources"]:
                matches = [
                    ref for ref in refs
                    if ref.provider == source["provider"]
                    and ref.collected_utc_ns == source["collected_utc_ns"]
                    and ref.digest == source["snapshot_sha256"]
                ]
                if len(matches) != 1:
                    raise ValueError("pinned provider snapshot does not resolve uniquely")
                ref = matches[0]
                sources.append((ref, records(ref)))
                hashes[str(ref.path)] = digest(ref.path)
            doc = fast.load_documents(dict(config=plan["config"], inputs=[entry]))[0]
            model = fast.Stationary(doc, plan["config"])
            x = np.asarray([*unit["x"][:2], unit["x"][input_index + 2]], dtype=float)
            receiver, _ = fast.baseline.site(*model.coordinates(x))
            hi = min(max(int(np.searchsorted(model.taus, x[2], side="right")), 1), len(model.taus) - 1)
            lo = hi - 1
            taus = model.taus[[lo, hi]]
            weight = (x[2] - taus[0]) / (taus[1] - taus[0])
            for track in doc["tracks"]:
                case = by_track.get((doc["session_id"], track["track_id"]))
                if case is None:
                    continue
                number = int(case["number"])
                choices = [
                    (epoch_ns(source_records[number].first_line), ref.collected_utc_ns,
                     ref.digest, ref, source_records[number])
                    for ref, source_records in sources if number in source_records
                ]
                if not choices:
                    raise ValueError("retained candidate missing from pinned provider snapshots")
                epoch, _, _, selected_ref, record = max(choices, key=lambda value: value[:3])
                age_days = (int(case["start_utc_ns"]) - int(epoch)) / (86400.0 * 1e9)
                if age_days < 0 or not np.isfinite(age_days):
                    raise ValueError("future or invalid selected element epoch")
                sha = element_digest(record)
                key = (unit["unit_id"], case["session_id"], case["track_id"], number)
                if unit["role"] == "target":
                    existing = target_rows.get(key)
                    if existing is None or existing["baseline_element_sha256"] != sha:
                        raise ValueError("target age binding differs from exact replay")
                    target_count += 1
                else:
                    position, velocity, valid = propagate_candidate_states(
                        parse_element_sets(record.text), [0], int(case["start_utc_ns"]),
                        np.asarray(case["times"], dtype=float), taus,
                    )
                    if valid.tolist() != [0] or not np.isfinite(position).all() or not np.isfinite(velocity).all():
                        raise ValueError("donor exact element propagation failed")
                    slot = mapping[(case["session_id"], case["track_id"])].index(number)
                    dp = float(np.max(abs(position[0] - track["candidate_position_km"][slot, [lo, hi]])))
                    dv = float(np.max(abs(velocity[0] - track["candidate_velocity_km_s"][slot, [lo, hi]])))
                    base = prediction(position[0], velocity[0], receiver, weight)
                    residual = np.asarray(case["residual"], dtype=float)
                    df = float(np.max(abs(track["y"] - base - residual)))
                    if not np.isfinite([dp, dv, df]).all() or dp > 1e-8 or dv > 1e-10 or df > 1e-6:
                        raise ValueError(f"donor exact replay failed: {key} {dp} {dv} {df}")
                    maxima = np.maximum(maxima, [dp, dv, df])
                    donor_count += 1
                output_rows.append(dict(
                    unit_id=unit["unit_id"], role=unit["role"], dataset=dataset,
                    session_id=case["session_id"], track_id=case["track_id"], number=number,
                    rf_hz=float(case["rf_hz"]), start_utc_ns=int(case["start_utc_ns"]),
                    element_epoch_utc_ns=int(epoch), age_days=float(age_days),
                    element_sha256=sha, provider=selected_ref.provider,
                    snapshot_collected_utc_ns=selected_ref.collected_utc_ns,
                    snapshot_sha256=selected_ref.sha256,
                ))
            del doc, model
        print(unit["unit_id"], donor_count, target_count, flush=True, file=sys.stderr)
    if donor_count != 9968 or target_count != 3983 or len(output_rows) != 13951:
        raise ValueError("unexpected retained-case coverage")
    if len({(r["unit_id"], r["session_id"], r["track_id"], r["number"]) for r in output_rows}) != len(output_rows):
        raise ValueError("duplicate output age binding")
    fixed_sources = [
        Path(__file__), HERE / "AGE_SCALE_PROTOCOL.md", HERE / "age_scale.py", plan_path,
        RECURRENCE, TARGET_REPLAY,
    ]
    for path in fixed_sources:
        hashes[str(path.relative_to(ROOT))] = digest(path)
    runtime = {
        str(Path(inspect.getfile(item))): digest(Path(inspect.getfile(item)))
        for item in (TleArchiveReader, parse_element_sets, propagate_candidate_states)
    }
    result = dict(
        schema="ds11-age-scale-exact-bindings/v1",
        status="preflight_passed",
        donor_cases=donor_count,
        target_cases=target_count,
        unique_snapshots=len({(r["provider"], r["snapshot_collected_utc_ns"], r["snapshot_sha256"]) for r in output_rows}),
        donor_maximum_replay_difference=dict(position_km=float(maxima[0]), velocity_km_s=float(maxima[1]), frequency_hz=float(maxima[2])),
        target_replay_source_maximum_difference=target_replay["max_baseline_difference"],
        elapsed_seconds=time.monotonic() - started,
        rows=output_rows,
        source_sha256=hashes,
        runtime_sha256=runtime,
    )
    output = HERE / "age-bindings.json"
    with output.open("x") as stream:
        json.dump(result, stream, separators=(",", ":"), allow_nan=False)
    print(json.dumps({key: value for key, value in result.items() if key != "rows" and key not in ("source_sha256", "runtime_sha256")}, indent=2))


if __name__ == "__main__":
    main()
