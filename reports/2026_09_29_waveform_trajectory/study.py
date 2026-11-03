"""Matched trajectory prediction against independent held-visit pilot symbols."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OLD = HERE.parent / "2026_09_29_training_waveform"
HEADER = HERE.parent / "2026_09_27_ds7_header"
sys.path[:0] = [str(OLD), str(HEADER)]
from convention import remove_upconversion_phase  # noqa: E402
from estimator import errors, fit  # noqa: E402
from tcodes import demodulate, geometry, references  # noqa: E402


def extrapolate(times, frequencies, target):
    assert len(times) == len(frequencies) == 2 and times[1] > times[0]
    return frequencies[0] + (frequencies[1] - frequencies[0]) * (
        (target - times[0]) / (times[1] - times[0])
    )


def frames_for(row):
    assert row["status"] == "ok", row.get("reason")
    path = ROOT / row["path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == row["sha256"]
    iq = np.load(path)
    x = iq[:, 0].astype(float) + 1j * iq[:, 1]
    fs = row["sample_rate_hz"]
    _, pb, center = geometry(row["edge"])
    _, _, pilot = references(row["edge"])
    candidate = row["candidate"]
    cfo = candidate["fractional_tracking_cfo_hz"]
    epoch = candidate["integer_epoch_sample"] + candidate["fractional_epoch_offset_samples"]
    rf = np.fft.fftfreq(1024, 1 / 240e6)
    keep = abs(rf[pb] - center + cfo) <= 0.45 * fs
    pb, pilot = pb[keep], pilot[:, keep]
    assert len(pb) >= 2
    frames = []
    for n in range(8):
        ep = epoch + n * fs / 750
        start = max(0, int(ep) - round(fs * 10e-6))
        stop = start + round(fs * 0.00137)
        assert stop <= len(x)
        symbols = demodulate(x[start:stop], fs, ep - start, cfo, center)[1:]
        frames.append(remove_upconversion_phase(symbols[:, pb] / pilot, center))
    return np.asarray(frames)


def main():
    plan = json.loads((HERE / "plan.json").read_text())
    inventory = json.loads((HERE / "inventory.json").read_text())
    for doc in (plan, inventory):
        for name, digest in doc["hashes"].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest
    expected = {(r["unit_id"], r["receiver_id"]) for r in plan["selections"]}
    assert len(inventory["rows"]) == len(expected)
    assert {(r["unit_id"], r["receiver_id"]) for r in inventory["rows"]} == expected
    groups = {}
    for row in inventory["rows"]:
        groups.setdefault((row["panel_id"], row["receiver_id"]), {})[row["role"]] = row
    results = []
    for (panel, rx), group in groups.items():
        result = dict(panel_id=panel, receiver_id=rx, status="ok")
        try:
            a, b, h = [group[role] for role in ("A", "B", "H")]
            assert a["edge"] == b["edge"] == h["edge"]
            frames = [frames_for(r) for r in (a, b, h)]
            corrections = [fit(y, np.arange(20, 220)) for y in frames]
            times = [r["time_s"] for r in (a, b, h)]
            assert times[0] < times[1] < times[2]
            anchor_rf = a["actual_rf_hz"]
            cached = [
                r["actual_rf_hz"] - anchor_rf + r["candidate"]["fractional_tracking_cfo_hz"]
                for r in (a, b, h)
            ]
            # Only the first two observations determine either trajectory.
            baseline = extrapolate(times[:2], cached[:2], times[2]) - cached[2]
            refined = (
                extrapolate(times[:2], np.asarray(cached[:2]) + corrections[:2], times[2])
                - cached[2]
            )
            frequencies = dict(
                cached_trajectory=float(baseline),
                long_trajectory=float(refined),
                cached_held=0.0,
                local_long_held=float(corrections[2]),
            )
            result.update(
                track_id=a["track_id"],
                times_s=times,
                visits=[r["visit"] for r in (a, b, h)],
                residual_corrections_hz=corrections,
                search_boundaries=[abs(f) >= 1499.999 for f in corrections],
                extrapolation_fraction=(times[2] - times[1]) / (times[1] - times[0]),
                slope_change_hz_s=(corrections[1] - corrections[0]) / (times[1] - times[0]),
                arms={
                    arm: dict(residual_frequency_hz=f, frame_nmse=errors(frames[2], f).tolist())
                    for arm, f in frequencies.items()
                },
            )
        except Exception as exc:
            result.update(status="failed", reason=f"{type(exc).__name__}: {exc}")
        results.append(result)
    summary = {}
    for ds in ("DS7", "DS8", "DS9", "all"):
        selected = [r for r in results if ds == "all" or r["panel_id"].startswith(ds)]
        valid = [r for r in selected if r["status"] == "ok"]
        gains = np.array(
            [
                np.mean(r["arms"]["cached_trajectory"]["frame_nmse"])
                - np.mean(r["arms"]["long_trajectory"]["frame_nmse"])
                for r in valid
            ]
        )
        summary[ds] = dict(
            planned=len(selected),
            returned=len(valid),
            improved=int((gains > 0).sum()),
            mean_gain=float(np.mean(gains)) if len(gains) else None,
            median_gain=float(np.median(gains)) if len(gains) else None,
            boundaries=sum(sum(r["search_boundaries"]) for r in valid),
            means={
                arm: float(np.mean([np.mean(r["arms"][arm]["frame_nmse"]) for r in valid]))
                if valid
                else None
                for arm in (
                    "cached_trajectory",
                    "long_trajectory",
                    "cached_held",
                    "local_long_held",
                )
            },
        )
    refs = (
        ROOT
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement/reference-template"
    )
    inputs = [HERE / n for n in ("plan.json", "inventory.json", "PROTOCOL.md", "study.py")]
    inputs += [OLD / n for n in ("estimator.py", "convention.py")]
    inputs += list(HEADER.glob("*.py"))
    inputs += [
        refs / "sssVec.mat",
        refs / "referenceTemplate.mat",
        ROOT / "tests/fixtures/qin_edge_pilots_appendix_a_v1.json",
    ]
    inputs += [ROOT / r["path"] for r in inventory["rows"] if r["status"] == "ok"]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs}
    (HERE / "results.json").write_text(
        json.dumps(dict(hashes=hashes, rows=results, summary=summary), indent=2, allow_nan=False)
        + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
