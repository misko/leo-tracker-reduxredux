"""Check zero-drift and longer pilot baselines without changing primary results."""

import json
import time

import numpy as np
from estimator import FIT, HELD, TS, WORDS, initial_frequency, rotation
from run import BASE, ROOT, demodulate, geometry, references, sha, slots
from scipy.optimize import minimize_scalar


def fixed_fit(y, mhz, coarse, training):
    t = training * TS

    def objective(f):
        g = np.mean(y[training] * rotation(t, mhz, [f, 0]).conj(), axis=0)
        return -float(np.sum(abs(g) ** 2))

    solution = minimize_scalar(objective, bounds=(coarse - 3000, coarse + 3000), method="bounded")
    return float(solution.x)


def error(y, mhz, f, training):
    g = np.mean(y[training] * rotation(training * TS, mhz, [f, 0]).conj(), axis=0)
    p = rotation(HELD * TS, mhz, [f, 0]) * g
    return float(np.sum(abs(y[HELD] - p) ** 2) / np.sum(abs(y[HELD]) ** 2))


def hybrid_fit(pilots, data, pm, dm, coarse):
    def objective(f):
        total = 0.0
        for y, mhz, idx in [(pilots, pm, np.arange(20, 220)), (data, dm, FIT)]:
            g = np.mean(y[idx] * rotation(idx * TS, mhz, [f, 0]).conj(), axis=0)
            total += len(idx) * float(np.sum(abs(g) ** 2))
        return -total

    return float(
        minimize_scalar(objective, bounds=(coarse - 3000, coarse + 3000), method="bounded").x
    )


def main():
    started = time.monotonic()
    primary = json.loads((BASE / "results.json").read_text())
    inventory = ROOT / "reports/2026_09_28_signal_clustering/local/inventory.json"
    members = json.loads(inventory.read_text())
    outputs = []
    for dataset, name in [("DS7", "S02"), ("DS8", "S13"), ("DS9", "DS9-middle")]:
        if dataset == "DS9":
            folder = ROOT / "reports/2026_09_28_sequence_semantics/local/ds9-middle-10m"
            streams = [
                dict(folder=folder, row=r)
                for r in json.loads((folder / "inventory.json").read_text())["exports"]
            ]
        else:
            streams = next(m for m in members if m["signal"] == name)["streams"]
        for rx, stream in enumerate(streams):
            from pathlib import Path

            folder, row = Path(stream["folder"]), stream["row"]
            path = folder / (row["name"] + ".npy")
            assert sha(path) == primary["input_sha256"][str(path)]
            raw = np.load(path)
            x = raw[:, 0].astype(float) + 1j * raw[:, 1]
            rate, edge = row["sample_rate_hz"], row["probe"]["edge"]
            bins, pb, center = geometry(edge)
            _, template, pilot = references(edge)
            c = row["candidate"]
            cfo = c["fractional_tracking_cfo_hz"]
            epoch = c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"]
            rf = np.fft.fftfreq(1024, 1 / 240e6)
            bins = bins[abs(rf[bins] - center + cfo) <= 0.45 * rate]
            mask = abs(rf[pb] - center + cfo) <= 0.45 * rate
            pb, pilot = pb[mask], pilot[:, mask]
            pm, dm = (rf[pb] - center) / 1e6, (rf[bins] - center) / 1e6
            mapping = slots(bins, np.arange(2, 302))
            for frame in range(12):
                original = next(
                    r
                    for r in primary["rows"]
                    if (r["dataset"], r["receiver"], r["frame"]) == (dataset, rx, frame)
                )
                ep = epoch + frame * rate / 750
                start = max(0, int(ep) - round(rate * 10e-6))
                sy = demodulate(
                    x[start : start + round(rate * 0.00137)], rate, ep - start, cfo, center
                )[1:]
                p = sy[:, pb] / pilot
                d = sy[:, bins] * template[bins, 1:].T.conj() * WORDS[original["state"], mapping]
                coarse, _ = initial_frequency(p)
                arms = {}
                for arm, y, mhz, training in [
                    ("pilot_fixed", p, pm, FIT),
                    ("sequence_fixed", np.c_[p, d], np.r_[pm, dm], FIT),
                    ("pilot_long", p, pm, np.arange(20, 220)),
                ]:
                    f = fixed_fit(y, mhz, coarse, training)
                    arms[arm] = dict(
                        frequency_hz=f,
                        held_pilot_nmse=error(p, pm, f, training),
                        held_sequence_nmse=error(d, dm, f, FIT),
                    )
                f = hybrid_fit(p, d, pm, dm, coarse)
                arms["hybrid_long"] = dict(
                    frequency_hz=f,
                    held_pilot_nmse=error(p, pm, f, np.arange(20, 220)),
                    held_sequence_nmse=error(d, dm, f, FIT),
                )
                outputs.append(
                    dict(
                        dataset=dataset,
                        receiver=rx,
                        frame=frame,
                        qualified=original["qualified"],
                        arms=arms,
                    )
                )
    (BASE / "followup-results.json").write_text(
        json.dumps(
            dict(
                rows=outputs,
                primary_sha256=sha(BASE / "results.json"),
                elapsed_seconds=time.monotonic() - started,
                source_sha256={
                    str(p): sha(p) for p in [BASE / "followup.py", BASE / "FOLLOWUP_PROTOCOL.md"]
                },
            ),
            indent=2,
        )
        + "\n"
    )
    print("Fixed-drift replay complete:", len(outputs))


if __name__ == "__main__":
    main()
