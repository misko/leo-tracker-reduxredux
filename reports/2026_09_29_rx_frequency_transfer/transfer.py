"""Paired-frequency transfer with past-only offset and held waveform validation."""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
sys.path.insert(0, str(ROOT / "reports/2026_09_29_sequence_long_support"))
sys.path.insert(0, str(ROOT / "reports/2026_09_29_sequence_estimator"))
from estimator import initial_frequency  # noqa: E402
from run import demodulate, geometry, references  # noqa: E402
from study import PILOT_TRAIN, error, fit  # noqa: E402


def offset_and_predictions(frequencies):
    """Input rows RX, columns frame; only first 30 frames estimate the offset."""
    difference = frequencies[1] - frequencies[0]
    offset = float(np.median(difference[:30]))
    mad = float(np.median(abs(difference[:30] - offset)))
    own = frequencies[:, 30:]
    peer = own[::-1].copy()
    peer[0] -= offset
    peer[1] += offset
    return (
        offset,
        mad,
        dict(
            own=own,
            blend=(own + peer) / 2,
            zero_offset=(own + own[::-1]) / 2,
            shuffled=(own + np.roll(peer, 13, axis=1)) / 2,
        ),
    )


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    started = time.monotonic()
    out = BASE / "local"
    out.mkdir(exist_ok=True)
    ip = ROOT / "reports/2026_09_28_signal_clustering/local/inventory.json"
    members = json.loads(ip.read_text())
    bindings = {str(ip): sha(ip)}
    visits = []
    for ds, names in [("DS7", ["S02", "S31", "S32"]), ("DS8", ["S13", "S28", "S29"])]:
        for name in names:
            m = next(x for x in members if x["signal"] == name)
            visits.append((ds, name, [(Path(s["folder"]), s["row"]) for s in m["streams"]]))
    for tag in ["middle", "first"]:
        folder = ROOT / f"reports/2026_09_28_sequence_semantics/local/ds9-{tag}-10m"
        ip = folder / "inventory.json"
        bindings[str(ip)] = sha(ip)
        visits.append(
            ("DS9", f"DS9-{tag}", [(folder, r) for r in json.loads(ip.read_text())["exports"]])
        )
    rows = []
    summaries = []
    for ds, name, streams in visits:
        arrays = []
        frequencies = []
        cofs = []
        quality = []
        origins = []
        rates = []
        edges = []
        for folder, row in streams:
            path = folder / (row["name"] + ".npy")
            raw = np.load(path)
            assert hashlib.sha256(raw.tobytes()).hexdigest() == row["excerpt_sha256"]
            bindings[str(path)] = sha(path)
            rate = row["sample_rate_hz"]
            edge = row["probe"]["edge"]
            c = row["candidate"]
            cfo = c["fractional_tracking_cfo_hz"]
            epoch = c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"]
            origins.append(epoch / rate)
            rates.append(rate)
            edges.append(edge)
            cofs.append(cfo)
            _, pb, center = geometry(edge)
            _, _, pilot = references(edge)
            rf = np.fft.fftfreq(1024, 1 / 240e6)
            mask = abs(rf[pb] - center + cfo) <= 0.45 * rate
            pb, pilot = pb[mask], pilot[:, mask]
            assert len(pb) >= 2
            x = raw[:, 0].astype(float) + 1j * raw[:, 1]
            ys = []
            fs = []
            qs = []
            for frame in range(80):
                ep = epoch + frame * rate / 750
                start = max(0, int(ep) - round(rate * 10e-6))
                stop = start + round(rate * 0.00137)
                assert stop <= len(x)
                sy = demodulate(x[start:stop], rate, ep - start, cfo, center)[1:, pb] / pilot
                coarse, q = initial_frequency(sy)
                fs.append(cfo + fit([(sy, PILOT_TRAIN)], coarse))
                qs.append(q)
                ys.append(sy)
            arrays.append(np.array(ys))
            frequencies.append(fs)
            quality.append(qs)
        assert rates[0] == rates[1] and edges[0] == edges[1]
        assert abs(origins[0] - origins[1]) < 0.0001, (name, origins)
        frequencies = np.array(frequencies)
        offset, mad, predictions = offset_and_predictions(frequencies)
        qualified = bool(mad < 100 and all(np.median(q[:30]) > 0.5 for q in quality))
        delta = frequencies[1] - frequencies[0]
        for rx in [0, 1]:
            for j, frame in enumerate(range(30, 80)):
                scores = {
                    arm: error(arrays[rx][frame], PILOT_TRAIN, float(values[rx, j] - cofs[rx]))
                    for arm, values in predictions.items()
                }
                rows.append(
                    dict(
                        dataset=ds,
                        signal=name,
                        receiver=rx,
                        frame=frame,
                        qualified=qualified,
                        nmse=scores,
                        frequency_hz=float(frequencies[rx, frame]),
                    )
                )
        summaries.append(
            dict(
                dataset=ds,
                signal=name,
                session=streams[0][1]["session_id"],
                qualified=qualified,
                offset_hz=offset,
                train_difference_mad_hz=mad,
                held_difference_residual_median_abs_hz=float(np.median(abs(delta[30:] - offset))),
                held_uncorrected_difference_median_abs_hz=float(np.median(abs(delta[30:]))),
                origin_difference_us=(origins[1] - origins[0]) * 1e6,
                training_pilot_coherence=[float(np.median(q[:30])) for q in quality],
                frequencies=frequencies.tolist(),
            )
        )
        np.savez_compressed(out / f"{name}-pilots.npz", rx0=arrays[0], rx1=arrays[1])
        print(
            name,
            "offset",
            round(offset, 2),
            "MAD",
            round(mad, 2),
            "qualified",
            qualified,
            flush=True,
        )
    for p in [
        BASE / "transfer.py",
        BASE / "PROTOCOL.md",
        ROOT / "reports/2026_09_29_sequence_long_support/study.py",
        ROOT / "reports/2026_09_29_sequence_estimator/estimator.py",
        ROOT / "reports/2026_09_29_sequence_estimator/run.py",
        ROOT / "tests/fixtures/qin_edge_pilots_appendix_a_v1.json",
    ]:
        bindings[str(p)] = sha(p)
    for name in ["tcodes", "analyze", "recover"]:
        p = ROOT / f"reports/2026_09_27_ds7_header/{name}.py"
        bindings[str(p)] = sha(p)
    refs = (
        ROOT
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement/reference-template"
    )
    for name in ["sssVec.mat", "referenceTemplate.mat"]:
        p = refs / name
        bindings[str(p)] = sha(p)
    (BASE / "results.json").write_text(
        json.dumps(
            dict(
                rows=rows,
                visits=summaries,
                input_sha256=bindings,
                seconds=time.monotonic() - started,
                python=sys.version,
                numpy=np.__version__,
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
