"""Read-only, post-hoc inspection of the two whole-domain 40-degree exclusions.

No new model fit, propagation, provider fetch, or raw-waveform access.
"""

import hashlib
import json
import platform
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris

from leo.operations.tle_archive import TleArchiveReader
from leo.sky.propagation import parse_element_set_records

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORTS = HERE.parent
FEAS = REPORTS / "2026_09_29_cone_feasibility"
TREND = REPORTS / "2026_09_29_unassociated_trend"
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(REPORTS / "2026_09_29_rx_cone_consistency"))
sys.path.insert(0, str(TREND))
import ds7_fast_baseline_adapter as baseline  # noqa: E402
from cones import axes, enu_los  # noqa: E402
from ds7_baseline_adapter import site  # noqa: E402
from trend_mixture import TrendMixturePosition  # noqa: E402

EXPECTED, BINDINGS = {}, {}
for report in (FEAS, TREND, REPORTS / "2026_09_29_cone_trend"):
    path = report / "evidence-sha256.json"
    payload = path.read_bytes()
    BINDINGS[str(path.relative_to(ROOT))] = hashlib.sha256(payload).hexdigest()
    for name, value in json.loads(payload)["sha256"].items():
        if name in EXPECTED:
            assert EXPECTED[name] == value, name
        EXPECTED[name] = value


def bind(path):
    name = str(path.relative_to(ROOT))
    value = hashlib.sha256(path.read_bytes()).hexdigest()
    assert EXPECTED[name] == value, name
    BINDINGS[name] = value


def read(path):
    bind(path)
    return json.loads(path.read_text())


def main():
    for module in (
        baseline,
        sys.modules["ds7_baseline_adapter"],
        sys.modules["cones"],
        sys.modules["trend_mixture"],
        sys.modules["contrast_position"],
    ):
        bind(Path(module.__file__))
    plan = read(FEAS / "plan.json")
    archive = TleArchiveReader(Path("/var/lib/leo/tle"))
    snapshots = archive.list_snapshots()
    counters = Counter()
    targets = []
    for unit in plan["units"]:
        if unit["group"]["source_dataset"] != "DS9" or unit["group"]["size"] != 8:
            continue
        evidence = read(FEAS / "runs" / unit["unit_id"] / "result.json")
        observations = {}
        inputs = {i["session_id"]: i for i in unit["group"]["inputs"]}
        for sid, item in inputs.items():
            path = Path(next(a["path"] for a in item["artifacts"] if a["kind"] == "observations"))
            observations[sid] = read(path)
        for r in evidence["rows"]:
            doc = observations[r["session_id"]]
            row = next(t for t in doc["tracks"] if t["track_id"] == r["track_id"])
            counters[int(row["receiver_id"]), row["channel"], row["rf_hz"]] += 1
            if r["widths"][2]["track_excluded"]:
                targets.append((unit, r, inputs[r["session_id"]]))
    assert sum(counters.values()) == 1460 and len(targets) == 2
    results = []
    for unit, exclusion, item in targets:
        sid, tid = exclusion["session_id"], exclusion["track_id"]
        for a in item["artifacts"]:
            bind(Path(a["path"]))
        doc = baseline.load_documents({"config": plan["config"], "inputs": [item]})[0]
        track = next(t for t in doc["tracks"] if t["track_id"] == tid)
        single = {**doc, "tracks": [track]}
        parent = TREND / "runs" / (unit["unit_id"] + "_q020")
        selected = read(parent / "selection.json")["selected"]
        prior = read(parent / "held/result.json")
        assert prior["audit_passed"]
        old = next(r for r in prior["rows"] if r["session_id"] == sid and r["track_id"] == tid)
        local = selected["x"][:2] + [selected["x"][2 + selected["session_ids"].index(sid)]]
        model = TrendMixturePosition([single], plan["config"], baseline.Stationary, 0.2)
        replay = model.evaluate(local, gradient=False, held=True)["rows"][0]
        for key in ("training_log_score", "held_log_score", "signal_responsibility"):
            assert abs(replay[key] - old[key]) < 1e-7
        np.testing.assert_allclose(
            replay["weights_given_signal"], old["weights_given_signal"], atol=1e-12
        )
        manifest_path = Path(
            next(a["path"] for a in item["artifacts"] if a["path"].endswith("manifest.json"))
        )
        manifest = read(manifest_path)
        index = next(r["index"] for r in manifest["tracks"] if r["track_id"] == tid)
        bank_path = Path(next(a["path"] for a in item["artifacts"] if a["path"].endswith(".npz")))
        with np.load(bank_path, allow_pickle=False) as bank:
            ids = bank[f"candidate_ids_{index}"].copy()
        source = next(
            s
            for s in manifest["provider_sources"]
            if s["snapshot_sha256"] == manifest["baseline_snapshot_sha256"]
        )
        snapshot = next(
            s
            for s in snapshots
            if s.digest == source["snapshot_sha256"]
            and s.provider == source["provider"]
            and s.collected_utc_ns == source["collected_utc_ns"]
        )
        raw = archive.read(snapshot)
        payload, _ = exclude_labelled_starlink_debris(raw)
        records = list(parse_element_set_records(payload))
        assert len(records) == manifest["catalogue_size"] == 11130
        assert np.issubdtype(ids.dtype, np.integer) and np.all((ids >= 0) & (ids < len(records)))
        lat, lon = model.coordinates(local)
        receiver, _ = site(lat, lon)
        los = enu_los(
            track["candidate_position_km"],
            plan["config"]["timing_grid_s"],
            local[2],
            receiver,
            lat,
            lon,
        )
        angles = np.degrees(
            np.arccos(np.clip(los @ axes("nominal")[int(track["receiver_id"])], -1, 1))
        )
        mask, times, y = track["mask"], np.asarray(track["times_s"]), track["y"]
        prediction, visible = model.models[0].prediction(track, local)
        weights = np.asarray(old["weights_given_signal"])
        assert len(ids) == len(weights) == len(angles)
        assert np.all(
            np.asarray(exclusion["candidate_lower_bounds_deg"])
            <= angles[:, mask].max(axis=1) + 1e-7
        )
        order = np.argsort(-weights, kind="stable")
        winner = int(order[0])
        residual = y - prediction[winner]
        offset = residual[mask].mean()
        candidates = []
        for j in order:
            record = records[int(ids[j])]
            candidates.append(
                {
                    "bank_index": int(ids[j]),
                    "catalog_number": int(record.satellite_number),
                    "name": record.name,
                    "training_weight_given_signal": float(weights[j]),
                    "horizon_visible": bool(visible[j]),
                    "training_max_angle_deg": float(angles[j, mask].max()),
                    "held_max_angle_deg": float(angles[j, ~mask].max()),
                    "domain_angle_lower_bound_deg": exclusion["candidate_lower_bounds_deg"][j],
                }
            )
        slope = float(np.polyfit(times[mask] - times[mask].mean(), y[mask], 1)[0])
        first = int(np.flatnonzero(mask)[0])
        results.append(
            {
                "panel": unit["unit_id"],
                "session_id": sid,
                "track_id": tid,
                "receiver_id": int(track["receiver_id"]),
                "channel": track["channel"],
                "rf_hz": track["rf_hz"],
                "observations": len(times),
                "training_observations": int(mask.sum()),
                "held_observations": int((~mask).sum()),
                "span_s": float(np.ptp(times)),
                "strictly_increasing_times": bool(np.all(np.diff(times) > 0)),
                "start_utc_ns": doc["start_utc_ns"],
                "first_observation_utc": datetime.fromtimestamp(
                    doc["start_utc_ns"] / 1e9 + times[0], UTC
                ).isoformat(),
                "training_slope_hz_s": slope,
                "signal_responsibility": old["signal_responsibility"],
                "training_log_score": old["training_log_score"],
                "held_log_score": old["held_log_score"],
                "replay_passed": True,
                "no_cone_selected_point": local,
                "catalogue_size": len(records),
                "base_snapshot": source,
                "candidates": candidates,
                "conditional_MAP_train_offset_hz": float(offset),
                "conditional_MAP_train_rms_hz": float(
                    np.sqrt(np.mean((residual[mask] - offset) ** 2))
                ),
                "conditional_MAP_held_rms_hz": float(
                    np.sqrt(np.mean((residual[~mask] - offset) ** 2))
                ),
                "times_s": times.tolist(),
                "training_mask": mask.tolist(),
                "visits": track["visits"],
                "observed_contrasts_hz": (y - y[first]).tolist(),
                "MAP_predicted_contrasts_hz": (
                    prediction[winner] - prediction[winner, first]
                ).tolist(),
                "MAP_angles_deg": angles[winner].tolist(),
            }
        )
    for name, value in BINDINGS.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == value
    output = {
        "exploratory_selection": (
            "All two tracks excluded everywhere at 40 degrees; not a random or independent sample"
        ),
        "python": platform.python_version(),
        "numpy": np.__version__,
        "denominator_tracks": 1460,
        "groups": [
            {"receiver_id": k[0], "channel": k[1], "rf_hz": k[2], "tracks": v}
            for k, v in sorted(counters.items())
        ],
        "targets": results,
        "input_sha256": BINDINGS,
    }
    with (HERE / "inspection.json").open("x") as f:
        json.dump(output, f, indent=2, allow_nan=False)
    print(
        "Verified two target replays and",
        sum(counters.values()),
        "DS9 denominator tracks",
        flush=True,
    )


if __name__ == "__main__":
    main()
