"""Describe waveform prediction and correction shape without fitting position."""
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ARMS = ("pilot_2_65", "pilot_22_221")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def shape_summary(times, corrections):
    t, y = np.asarray(times, dtype=float), np.asarray(corrections, dtype=float)
    assert len(t) == len(y) and np.isfinite(t).all() and np.isfinite(y).all()
    if not len(y):
        return None
    centered = y - np.median(y)
    z = t - np.mean(t)
    slope = float(np.dot(z, y - np.mean(y)) / np.dot(z, z)) if np.dot(z, z) else None
    return dict(count=len(y), median_correction_hz=float(np.median(y)),
                centered_rms_hz=float(np.sqrt(np.mean(centered**2))),
                centered_absolute_p90_hz=float(np.quantile(abs(centered), .9)),
                diagnostic_linear_slope_hz_s=slope)


def summarize(plan_rows, measurements):
    assert len(plan_rows) == len(measurements) == 111
    groups = {}
    for planned, measured in zip(plan_rows, measurements, strict=True):
        for key in ("ordinal", "track_id", "observation_index", "visit"):
            assert planned[key] == measured[key]
        groups.setdefault(planned["track_id"], []).append((planned, measured))
    groups["all"] = list(zip(plan_rows, measurements, strict=True))
    result = {}
    for key, pairs in groups.items():
        counts = {}
        for _, row in pairs:
            assert row["status"] not in ("pending", "measuring")
            counts[row["status"]] = counts.get(row["status"], 0) + 1
        valid = [(p, r) for p, r in pairs if r["status"] == "ok"]
        row = dict(planned=len(pairs), status_counts=counts, arms={})
        for arm in ARMS:
            gains, corrections, times = [], [], []
            boundaries = 0
            for p, r in valid:
                a = r["arms"][arm]
                base = np.asarray(r["arms"]["cached"]["frame_nmse_symbols_222_301"])
                new = np.asarray(a["frame_nmse_symbols_222_301"])
                assert base.shape == new.shape == (8,)
                assert np.isfinite(base).all() and np.isfinite(new).all()
                assert a["additive_alias"] == p["additive_alias"]
                assert abs(a["canonical_delta_hz"] - a["native_residual_hz"]*11.2e9/p["actual_rf_hz"]) < 1e-9
                gains.append(float(np.mean(base-new)))
                boundaries += a["search_boundary"]
                corrections.append(a["canonical_delta_hz"])
                times.append(p["time_s"])
            row["arms"][arm] = dict(
                excerpts_improved=sum(g > 0 for g in gains), search_boundaries=boundaries,
                mean_excerpt_nmse_gain=float(np.mean(gains)) if gains else None,
                median_excerpt_nmse_gain=float(np.median(gains)) if gains else None,
                correction_shape=shape_summary(times, corrections) if key != "all" else None)
        result[key] = row
    return result


def main():
    plan_path = HERE / "manifest.json"
    extraction_path = HERE / "local/extraction.json"
    measurements_path = HERE / "local/measurements.json"
    plan, extraction, measured = [json.loads(p.read_text()) for p in
                                 (plan_path, extraction_path, measurements_path)]
    for path, expected in plan["sources"].items():
        assert digest(path) == expected
    assert extraction["plan_sha256"] == measured["plan_sha256"] == digest(plan_path)
    assert measured["extraction_sha256"] == digest(extraction_path)
    for row in extraction["rows"]:
        if row["status"] == "ok":
            assert digest(row["path"]) == row["sha256"]
    receipts = sorted((HERE / "attempts").glob("*.receipt.json"))
    assert len([p for p in receipts if p.name.startswith("measure-")]) == 1
    for path in receipts:
        assert json.loads(path.read_text())["plan_sha256"] == digest(plan_path)
    paths = [plan_path, extraction_path, measurements_path, Path(__file__),
             HERE / "test_assess_measurements.py"] + receipts
    result = dict(schema="ds11-waveform-measurement-summary/v1", reference_used=False,
                  position_fit_performed=False, summary=summarize(plan["rows"], measured["rows"]),
                  sources={str(p.resolve()):digest(p) for p in paths})
    with (HERE / "measurement_summary.json").open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    print(json.dumps(result["summary"], indent=2))


if __name__ == "__main__":
    main()
