"""Validate forecast membership, timing, geometry and retained probability mass."""
import hashlib
import json
import math
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    partition = json.loads((ROOT / "partitions.json").read_text())
    bank = json.loads((ROOT / "candidate-bank.json").read_text())
    windows = {r["source_window_id"]: r for r in partition["windows"]}
    records = {r["session_id"]: r for r in partition["recordings"]}
    masses, prediction_count = [], 0
    track_counts = {}
    target_counts = {}
    for track in bank["tracks"]:
        sid = track["session_id"]
        track_counts[sid] = track_counts.get(sid, 0) + 1
        assert track["training_end_utc_ns"] <= records[sid]["training_end_utc_ns"]
        expected = {
            wid for wid, w in windows.items()
            if w["session_id"] == sid and w["role"] in {"reception", "held_frequency"}
        }
        target_counts[sid] = len(expected)
        candidates = track["top_candidates"]
        assert 0 < len(candidates) <= 3
        probabilities = [c["conditional_top3_probability"] for c in candidates]
        assert math.isclose(sum(probabilities), 1.0, abs_tol=1e-10)
        mass = sum(c["catalogue_probability"] for c in candidates)
        assert 0 < mass <= 1.0 + 1e-10
        masses.append(mass)
        for candidate in candidates:
            predictions = candidate["window_predictions"]
            assert len(predictions) == len(expected)
            assert {p["source_window_id"] for p in predictions} == expected
            for prediction in predictions:
                window = windows[prediction["source_window_id"]]
                assert prediction["role"] == window["role"]
                assert prediction["prediction_utc_ns"] == window["window_midpoint_utc_ns"]
                assert prediction["prediction_utc_ns"] > track["training_end_utc_ns"]
                assert math.isfinite(prediction["predicted_hz"])
                assert math.isfinite(prediction["elevation_deg"])
                unit = prediction["los_enu_unit"]
                assert math.isclose(sum(x*x for x in unit.values()), 1.0, abs_tol=1e-10)
                assert prediction["visible"] == (prediction["elevation_deg"] >= 0)
            prediction_count += len(predictions)
    for recording in bank["recordings"]:
        sid = recording["session_id"]
        assert track_counts[sid] == recording["selected_training_tracks"] <= 3
        locators = recording["training_probe_locators"]
        assert len(locators) == recording["training_probes"]
        seen = set()
        for locator in locators:
            window = windows[locator["source_window_id"]]
            assert window["role"] == "train" and window["session_id"] == sid
            key = (locator["source_window_id"], locator["receiver_id"])
            assert key not in seen
            seen.add(key)
        expected_probes = {
            (wid, rx) for wid, w in windows.items()
            if w["session_id"] == sid and w["role"] == "train" for rx in (0, 1)
        }
        assert seen == expected_probes
    if bank["status"] == "complete":
        assert set(track_counts) == set(records)
        assert bank["raw_candidate_matching_ready"] is False
        assert bank["prediction_reference_rf_hz"] == 11_200_000_000.0
    output = {
        "bank_status": bank["status"],
        "recordings_completed": len(track_counts),
        "selected_tracks": sum(track_counts.values()),
        "tracks_by_recording": track_counts,
        "distinct_future_windows": sum(target_counts.values()),
        "candidate_track_window_predictions": prediction_count,
        "training_probe_filter_and_future_membership_verified": True,
        "exact_midpoint_and_unit_los_verified": True,
        "top3_conditional_probabilities_normalized": True,
        "retained_catalogue_probability_mass": {
            "minimum": min(masses), "median": statistics.median(masses), "maximum": max(masses)
        },
        "raw_detection_matching_evaluated": False,
        "input_hashes": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in ("partitions.json", "candidate-bank.json")
        },
    }
    (ROOT / "bank-audit.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
