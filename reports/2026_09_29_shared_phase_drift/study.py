import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from model import learn, prediction

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
REPORTS = HERE.parent
sys.path.insert(0, str(REPORTS / "2026_09_27_ds7_header"))
from tcodes import geometry  # noqa: E402


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def read(p):
    return json.loads(p.read_text())


def main():
    started = time.monotonic()
    priorpath = REPORTS / "2026_09_29_frequency_peak_tracking/results.json"
    prior = read(priorpath)
    for name, h in prior["input_sha256"].items():
        assert sha(Path(name)) == h, name
    transferpath = REPORTS / "2026_09_29_rx_frequency_transfer/results.json"
    transfer = read(transferpath)
    for name, h in transfer["input_sha256"].items():
        assert sha(Path(name)) == h, name
    inventory = REPORTS / "2026_09_28_signal_clustering/local/inventory.json"
    members = read(inventory)
    paths = [
        priorpath,
        transferpath,
        inventory,
        HERE / "study.py",
        HERE / "model.py",
        HERE / "PROTOCOL.md",
        REPORTS / "2026_09_27_ds7_header/tcodes.py",
    ]
    groups, rows = [], []
    for visit in transfer["visits"]:
        name = visit["signal"]
        if visit["dataset"] == "DS9":
            ip = REPORTS / f"2026_09_28_sequence_semantics/local/{name.lower()}-10m/inventory.json"
            metadata = read(ip)["exports"]
            paths.append(ip)
        else:
            metadata = [
                s["row"] for s in next(m for m in members if m["signal"] == name)["streams"]
            ]
        path = REPORTS / f"2026_09_29_rx_frequency_transfer/local/{name}-pilots.npz"
        paths.append(path)
        with np.load(path, allow_pickle=False) as cache:
            for rx, row in enumerate(metadata):
                values = cache[f"rx{rx}"]
                assert values.shape[0] == 80
                _, pb, center = geometry(row["probe"]["edge"])
                rf = np.fft.fftfreq(1024, 1 / 240e6)
                cfo = row["candidate"]["fractional_tracking_cfo_hz"]
                mask = abs(rf[pb] - center + cfo) <= 0.45 * row["sample_rate_hz"]
                mhz = (rf[pb[mask]] - center) / 1e6
                assert len(mhz) == values.shape[2]
                series = sorted(
                    [r for r in prior["series"] if r["signal"] == name and r["receiver"] == rx],
                    key=lambda r: r["frame"],
                )
                assert [r["frame"] for r in series] == list(range(80))
                coarse = np.array([r["frequencies"]["global_peak"] for r in series])
                fit = learn(values[:30], mhz, coarse[:30])
                drift = fit["drift_ppm"] if fit["qualified"] else 0.0
                groups.append(
                    dict(
                        dataset=visit["dataset"],
                        signal=name,
                        receiver=rx,
                        mhz=mhz.tolist(),
                        fit=fit,
                        applied_drift_ppm=drift,
                    )
                )
                for frame in range(30, 80):
                    arms = {
                        arm: prediction(values[frame], mhz, coarse[frame], d)
                        for arm, d in (("zero", 0.0), ("shared", drift), ("reversed", -drift))
                    }
                    rows.append(
                        dict(
                            dataset=visit["dataset"],
                            signal=name,
                            receiver=rx,
                            frame=frame,
                            arms=arms,
                        )
                    )
                print(name, rx, fit["qualified"], fit["drift_ppm"], flush=True)
    assert len(groups) == 16 and len(rows) == 800
    result = dict(
        groups=groups,
        rows=rows,
        hashes={str(p): sha(p) for p in paths},
        elapsed_seconds=time.monotonic() - started,
    )
    with (HERE / "results.json").open("x") as out:
        json.dump(result, out, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
