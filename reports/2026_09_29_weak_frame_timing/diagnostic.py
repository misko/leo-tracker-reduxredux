"""Small raw-IQ timing search with independently held pilot evaluation."""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
sys.path.insert(0, str(ROOT / "reports/2026_09_29_sequence_estimator"))
from estimator import INIT, TS, initial_frequency  # noqa: E402
from run import demodulate, geometry, references  # noqa: E402

HELD = np.arange(220, 300)


def train(y):
    f, q = initial_frequency(y)
    g = np.mean(y[INIT] * np.exp(-2j * np.pi * f * (INIT * TS)[:, None]), axis=0)
    return f, q, g


def evaluate(y, f, g):
    prediction = g * np.exp(2j * np.pi * f * (HELD * TS)[:, None])
    energy = max(float(np.sum(abs(y[HELD]) ** 2)), 1e-30)
    return dict(
        nmse=float(np.sum(abs(y[HELD] - prediction) ** 2) / energy),
        held_coherence=float(
            abs(np.sum(y[HELD] * prediction.conj()))
            / np.sqrt(energy * max(float(np.sum(abs(prediction) ** 2)), 1e-30))
        ),
    )


def choose(candidates):
    fits = [train(y) for y in candidates]
    index = int(np.argmax([v[1] for v in fits]))
    return index, fits


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    started = time.monotonic()
    inventory = ROOT / "reports/2026_09_28_signal_clustering/local/inventory.json"
    prior = ROOT / "reports/2026_09_29_frequency_peak_tracking/results.json"
    series = json.loads(prior.read_text())["series"]
    members = json.loads(inventory.read_text())
    hashes = {str(p): sha(p) for p in [inventory, prior]}
    rows = []
    for name in ["S31", "S32"]:
        member = next(m for m in members if m["signal"] == name)
        for rx, stream in enumerate(member["streams"]):
            row = stream["row"]
            p = Path(stream["folder"]) / (row["name"] + ".npy")
            raw = np.load(p)
            assert hashlib.sha256(raw.tobytes()).hexdigest() == row["excerpt_sha256"]
            hashes[str(p)] = sha(p)
            x = raw[:, 0].astype(float) + 1j * raw[:, 1]
            rate = row["sample_rate_hz"]
            edge = row["probe"]["edge"]
            c = row["candidate"]
            cfo = c["fractional_tracking_cfo_hz"]
            epoch = c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"]
            _, pb, center = geometry(edge)
            _, _, pilot = references(edge)
            rf = np.fft.fftfreq(1024, 1 / 240e6)
            mask = abs(rf[pb] - center + cfo) <= 0.45 * rate
            pb, pilot = pb[mask], pilot[:, mask]
            selection = [
                s for s in series if s["signal"] == name and s["receiver"] == rx and s["frame"] < 30
            ]
            weak = [s["frame"] for s in selection if s["candidates"][0]["score"] < 0.03][:4]
            strong = [s["frame"] for s in selection if s["candidates"][0]["score"] > 0.2][:4]
            assert len(weak) == len(strong) == 4
            shifts = [s * TS * rate + d for s in [-2, -1, 0, 1, 2] for d in [-1, -0.5, 0, 0.5, 1]]
            zero = shifts.index(0)
            for frame in sorted(weak + strong):
                ep = epoch + frame * rate / 750
                start = max(0, int(ep) - round(rate * 10e-6))
                stop = start + round(rate * 0.00137)
                sy = [
                    demodulate(x[start:stop], rate, ep - start + shift, cfo, center)[1:, pb]
                    for shift in shifts
                ]
                ys = [v / pilot for v in sy]
                best, fits = choose(ys)
                f, q, g = fits[best]
                wrong = sy[best] / np.roll(pilot, 17, axis=0)
                wf, wq, wg = train(wrong)
                lo = int(ep + 22 * TS * rate)
                hi = int(ep + 222 * TS * rate)
                rows.append(
                    dict(
                        signal=name,
                        receiver=rx,
                        frame=frame,
                        weak=frame in weak,
                        shift_samples=shifts[best],
                        shift_us=shifts[best] / rate * 1e6,
                        original_train_coherence=fits[zero][1],
                        selected_train_coherence=q,
                        original=evaluate(ys[zero], fits[zero][0], fits[zero][2]),
                        selected=evaluate(ys[best], f, g),
                        wrong=evaluate(wrong, wf, wg),
                        wrong_train_coherence=wq,
                        raw_mean_power=float(np.mean(abs(x[lo:hi]) ** 2)),
                        pilot_band_mean_power=float(np.mean(abs(sy[zero]) ** 2)),
                        trial_coherences=[v[1] for v in fits],
                    )
                )
            print(name, rx, "complete", flush=True)
    paths = [
        BASE / "diagnostic.py",
        BASE / "PROTOCOL.md",
        ROOT / "reports/2026_09_29_sequence_estimator/estimator.py",
        ROOT / "reports/2026_09_29_sequence_estimator/run.py",
        ROOT / "tests/fixtures/qin_edge_pilots_appendix_a_v1.json",
    ]
    paths += [
        ROOT / f"reports/2026_09_27_ds7_header/{n}.py" for n in ["analyze", "recover", "tcodes"]
    ]
    refs = (
        ROOT
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement/reference-template"
    )
    paths += [refs / "sssVec.mat", refs / "referenceTemplate.mat"]
    hashes.update({str(p): sha(p) for p in paths})
    (BASE / "results.json").write_text(
        json.dumps(
            dict(rows=rows, input_sha256=hashes, seconds=time.monotonic() - started), indent=2
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
