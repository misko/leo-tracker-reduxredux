"""Bounded known-pilot timing/alias diagnostic, with next-frame evaluation."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str((BASE.parents[3] / "reports") / "2026_09_28_ds7_ds8_correspondence"))
from native_rate_decode import TS, calibrate, demodulate, geometry, references  # noqa: E402


def main():
    folder = BASE / "local/ds9-first-10m"
    inventory = folder / "inventory.json"
    rows = []
    for row in json.loads(inventory.read_text())["exports"]:
        raw = np.load(folder / (row["name"] + ".npy"))
        assert hashlib.sha256(raw.tobytes()).hexdigest() == row["excerpt_sha256"]
        rate = row["sample_rate_hz"]
        candidate = row["candidate"]
        epoch = candidate["integer_epoch_sample"] + candidate["fractional_epoch_offset_samples"]
        _, pb, center = geometry(row["probe"]["edge"])
        _, _, pilot = references(row["probe"]["edge"])

        def measure(
            frame,
            timing,
            alias,
            *,
            epoch=epoch,
            rate=rate,
            raw=raw,
            candidate=candidate,
            center=center,
            pilot=pilot,
            pb=pb,
        ):
            ep = epoch + frame * rate / 750
            start = int(ep) - round(rate * 10e-6)
            samples = raw[start : start + round(rate * 0.00137)]
            x = samples[:, 0].astype(float) + 1j * samples[:, 1]
            sy = demodulate(
                x,
                rate,
                ep - start + timing,
                candidate["fractional_tracking_cfo_hz"] + alias / TS,
                center,
            )
            y, diagnostic = calibrate(sy, pilot, pb)
            train = y[21:, pb] / pilot[20:]
            return dict(
                training_coherence=float(abs(train.mean()) / np.sqrt(np.mean(abs(train) ** 2))),
                held_coherence=diagnostic["held_pilot_coherence"],
                phase_slope=diagnostic["phase_slope"],
            )

        trials = [dict(timing=0, alias=a, **measure(0, 0, a)) for a in (-2, -1, 0, 1, 2)]
        trials += [
            dict(timing=float(t), alias=0, **measure(0, t, 0))
            for t in (-2, -1.5, -1, -0.5, 0.5, 1, 1.5, 2)
        ]
        best = max(trials, key=lambda r: r["training_coherence"])
        result = dict(
            name=row["name"],
            discovery_frame=0,
            trials=trials,
            selected=best,
            evaluation_frame=1,
            evaluation_baseline=measure(1, 0, 0),
            evaluation_selected=measure(1, best["timing"], best["alias"]),
        )
        rows.append(result)
        print(
            result["name"],
            best,
            result["evaluation_baseline"],
            result["evaluation_selected"],
            flush=True,
        )
    output = dict(
        rows=rows,
        inventory_sha256=hashlib.sha256(inventory.read_bytes()).hexdigest(),
        limitation="Two frames per receiver, known pilots only. One-dimensional "
        "alias/timing probes, not a joint search or diagnosis of all impairments. "
        "Selection uses frame0 training pilots only; frame1 is evaluation. "
        "Original acquisition and soft-cache estimates are unchanged.",
    )
    (BASE / "local/ds9_calibration_probe.json").write_text(json.dumps(output, indent=2) + "\n")


if __name__ == "__main__":
    main()
