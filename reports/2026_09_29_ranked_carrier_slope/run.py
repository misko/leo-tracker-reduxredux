import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from model import errors, fit, objective

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SOURCE = HERE.parent / "2026_09_29_ranked_waveform_position"
HELPER = HERE.parent / "2026_09_29_waveform_trajectory"
sys.path.insert(0, str(HELPER))
from study import frames_for, geometry  # noqa: E402


def main():
    inventory = json.loads((SOURCE / "inventory.json").read_text())
    prior = json.loads((SOURCE / "measurements.json").read_text())
    for doc in (inventory, prior):
        for path, digest in doc["hashes"].items():
            assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
    saved = {(r["unit_id"], r["receiver_id"]): r for r in prior["rows"]}
    assert len(inventory["rows"]) == len(saved) == 72
    rows = []
    maximum_replay = 0.0
    for row in inventory["rows"]:
        result = {
            k: row[k]
            for k in ("unit_id", "panel_id", "receiver_id", "session_id", "track_id", "visit")
        }
        result["status"] = "ok"
        try:
            frames = frames_for(row)
            previous = saved[row["unit_id"], row["receiver_id"]]
            assert previous["status"] == "ok"
            f = previous["residual_frequency_hz"]
            _, bins, center = geometry(row["edge"])
            rf = np.fft.fftfreq(1024, 1 / 240e6)
            cfo = row["candidate"]["fractional_tracking_cfo_hz"]
            keep = abs(rf[bins] - center + cfo) <= 0.45 * row["sample_rate_hz"]
            offsets = (rf[bins[keep]] - center) / 1e6
            assert len(offsets) == frames.shape[2] >= 2
            common = errors(frames, offsets, [f, 0])
            cached = errors(frames, offsets, [0, 0])
            replay = max(
                float(np.max(abs(common - previous["refined_frame_nmse"]))),
                float(np.max(abs(cached - previous["cached_frame_nmse"]))),
            )
            assert replay < 1e-10
            maximum_replay = max(maximum_replay, replay)
            selected, starts = fit(frames, offsets, f)
            result.update(
                starts=starts,
                common_frequency_hz=f,
                cached_frame_nmse=cached.tolist(),
                common_frame_nmse=common.tolist(),
            )
            assert selected is not None, "no qualified joint fit"
            baseline_loss = objective([f / 1000, 0], frames, offsets)[0]
            assert selected["loss"] <= baseline_loss + 1e-10
            frequency, ppm = selected["parameters"]
            result.update(
                selected=selected,
                frequency_shift_hz=frequency - f,
                frequency_boundary=abs(frequency) >= 1499.999,
                slope_boundary=abs(ppm) >= 99.999,
                joint_frame_nmse=errors(frames, offsets, selected["parameters"]).tolist(),
            )
        except Exception as exc:
            result.update(status="failed", reason=f"{type(exc).__name__}: {exc}")
        rows.append(result)
    summary = {}
    for ds in ("DS7", "DS8", "DS9", "all"):
        chosen = [r for r in rows if ds == "all" or r["panel_id"].startswith(ds)]
        valid = [r for r in chosen if r["status"] == "ok"]
        gains = np.array(
            [np.mean(r["common_frame_nmse"]) - np.mean(r["joint_frame_nmse"]) for r in valid]
        )
        summary[ds] = dict(
            planned=len(chosen),
            returned=len(valid),
            improved=int(sum(gains > 1e-10)),
            mean_gain=float(np.mean(gains)) if valid else None,
            median_gain=float(np.median(gains)) if valid else None,
            mean_nmse={
                arm: float(np.mean([np.mean(r[f"{arm}_frame_nmse"]) for r in valid]))
                if valid
                else None
                for arm in ("cached", "common", "joint")
            },
            slope_boundaries=sum(r["slope_boundary"] for r in valid),
            frequency_boundaries=sum(r["frequency_boundary"] for r in valid),
            median_absolute_frequency_shift_hz=float(
                np.median([abs(r["frequency_shift_hz"]) for r in valid])
            )
            if valid
            else None,
            median_slope_ppm=float(np.median([r["selected"]["parameters"][1] for r in valid]))
            if valid
            else None,
        )
    paths = [
        SOURCE / "inventory.json",
        SOURCE / "measurements.json",
        HERE / "run.py",
        HERE / "model.py",
        HERE / "PROTOCOL.md",
    ]
    paths += [ROOT / p for p in prior["hashes"]]
    hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    (HERE / "results.json").write_text(
        json.dumps(
            dict(
                hashes=hashes,
                rows=rows,
                summary=summary,
                maximum_prior_replay_difference=maximum_replay,
            ),
            indent=2,
            allow_nan=False,
        )
        + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
