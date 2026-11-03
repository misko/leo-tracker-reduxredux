"""Past-only control envelope; unsupported frames stay in evaluation."""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
sys.path.insert(0, str(ROOT / "reports/2026_09_29_frequency_peak_tracking"))
sys.path.insert(0, str(ROOT / "reports/2026_09_29_sequence_estimator"))
from run import references  # noqa: E402
from tracking import PILOT_TRAIN, error, peaks  # noqa: E402


def threshold(control_scores):
    scores = np.asarray(control_scores, float)
    if scores.shape != (30, 3) or not np.isfinite(scores).all():
        raise ValueError("Require 30 frames and three finite control scores")
    return float(scores.max())


def decision(score, frequency, held_error, envelope):
    accepted = bool(score > envelope)
    return dict(
        accepted=accepted,
        frequency_hz=float(frequency) if accepted else None,
        nmse=float(held_error) if accepted else 1.0,
    )


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    started = time.monotonic()
    parent = ROOT / "reports/2026_09_29_frequency_peak_tracking/results.json"
    p = json.loads(parent.read_text())
    for path, expected in p["input_sha256"].items():
        assert sha(Path(path)) == expected, path
    inventory = ROOT / "reports/2026_09_28_signal_clustering/local/inventory.json"
    members = json.loads(inventory.read_text())
    bindings = {str(parent): sha(parent), str(inventory): sha(inventory)}
    rows = []
    groups = []
    for name in dict.fromkeys(r["signal"] for r in p["rows"]):
        if name.startswith("DS9-"):
            ip = (
                ROOT
                / "reports/2026_09_28_sequence_semantics/local"
                / f"ds9-{name.split('-')[1]}-10m/inventory.json"
            )
            source_rows = json.loads(ip.read_text())["exports"]
            bindings[str(ip)] = sha(ip)
        else:
            source_rows = [
                s["row"] for s in next(m for m in members if m["signal"] == name)["streams"]
            ]
        path = ROOT / f"reports/2026_09_29_rx_frequency_transfer/local/{name}-pilots.npz"
        assert sha(path) == p["input_sha256"][str(path)]
        bindings[str(path)] = sha(path)
        archive = np.load(path)
        for rx in [0, 1]:
            values = archive[f"rx{rx}"]
            _, _, pilot = references(source_rows[rx]["probe"]["edge"])
            assert values.shape == (80, 300, 8) and pilot.shape == (300, 8)
            controls = np.zeros((30, 3))
            for frame in range(30):
                for j, roll in enumerate([17, 41, 83]):
                    wrong = values[frame] * pilot / np.roll(pilot, roll, axis=0)
                    controls[frame, j] = peaks(wrong)[0]["score"]
            envelope = threshold(controls)
            groups.append(
                dict(signal=name, receiver=rx, threshold=envelope, control_scores=controls.tolist())
            )
            for frame in range(30, 80):
                s = next(
                    s
                    for s in p["series"]
                    if (s["signal"], s["receiver"], s["frame"]) == (name, rx, frame)
                )
                original = next(
                    r
                    for r in p["rows"]
                    if (r["signal"], r["receiver"], r["frame"]) == (name, rx, frame)
                )
                best = s["candidates"][0]
                baseline = error(values[frame], PILOT_TRAIN, best["frequency_hz"])
                assert abs(baseline - original["nmse"]["global_peak"]) < 1e-12
                wrong = values[frame] * pilot / np.roll(pilot, 17, axis=0)
                null = peaks(wrong)[0]
                rows.append(
                    dict(
                        signal=name,
                        dataset=original["dataset"],
                        receiver=rx,
                        frame=frame,
                        exact_score=best["score"],
                        wrong_score=null["score"],
                        wrong_accepted=bool(null["score"] > envelope),
                        baseline_nmse=baseline,
                        support=decision(best["score"], best["frequency_hz"], baseline, envelope),
                        fixed=decision(best["score"], best["frequency_hz"], baseline, 0.2),
                    )
                )
            print(name, rx, "threshold", round(envelope, 5), flush=True)
    for path in [
        BASE / "support.py",
        BASE / "PROTOCOL.md",
        ROOT / "reports/2026_09_29_frequency_peak_tracking/tracking.py",
        ROOT / "reports/2026_09_29_sequence_long_support/study.py",
        ROOT / "reports/2026_09_29_sequence_estimator/estimator.py",
        ROOT / "reports/2026_09_29_sequence_estimator/run.py",
        ROOT / "reports/2026_09_27_ds7_header/recover.py",
        ROOT / "tests/fixtures/qin_edge_pilots_appendix_a_v1.json",
    ]:
        bindings[str(path)] = sha(path)
    (BASE / "results.json").write_text(
        json.dumps(
            dict(
                rows=rows, groups=groups, input_sha256=bindings, seconds=time.monotonic() - started
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
