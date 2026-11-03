"""Longer generated-sequence support; held samples never choose a region."""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[1]
sys.path.insert(0, str(ROOT / "reports/2026_09_29_sequence_estimator"))
from estimator import TS, WORDS, initial_frequency  # noqa: E402
from run import demodulate, geometry, references, slots  # noqa: E402

PILOT_TRAIN = np.arange(20, 220)
HELD = np.arange(220, 300)


def gain(y, idx, f):
    return np.mean(y[idx] * np.exp(-2j * np.pi * f * (idx * TS)[:, None]), axis=0)


def coherence(y, idx, f):
    return float(
        np.sqrt(
            np.sum(abs(gain(y, idx, f)) ** 2)
            / max(np.mean(np.sum(abs(y[idx]) ** 2, axis=1)), 1e-30)
        )
    )


def fit(groups, coarse):
    def objective(f):
        return -sum(len(idx) * float(np.sum(abs(gain(y, idx, f)) ** 2)) for y, idx in groups)

    result = minimize_scalar(objective, bounds=(coarse - 1500, coarse + 1500), method="bounded")
    if not result.success:
        raise RuntimeError("Frequency fit failed")
    return float(result.x)


def error(y, idx, f):
    predicted = gain(y, idx, f) * np.exp(2j * np.pi * f * (HELD * TS)[:, None])
    return float(np.sum(abs(y[HELD] - predicted) ** 2) / max(np.sum(abs(y[HELD]) ** 2), 1e-30))


def estimate(pilots, data, mapping):
    coarse, pc = initial_frequency(pilots)
    baseline = fit([(pilots, PILOT_TRAIN)], coarse)
    candidates = []
    for first in [42, 82, 122, 162]:
        idx = np.arange(first - 2, 220, 2)
        z = data[idx] * np.exp(-2j * np.pi * baseline * (idx * TS)[:, None])
        means = np.mean(z[None] * WORDS[:, mapping[idx]], axis=1)
        scores = np.sum(abs(means) ** 2, axis=1) / max(np.mean(np.sum(abs(z) ** 2, axis=1)), 1e-30)
        state = int(np.argmax(scores))
        candidates.append((first, state, float(np.sqrt(scores[state]))))
    selected = next((c for c in candidates if c[2] > 0.5), max(candidates, key=lambda c: c[2]))
    first, state, sc = selected
    idx = np.arange(first - 1, 220, 2)
    seq = data * WORDS[state, mapping]
    vc = coherence(seq, idx, baseline)
    qualified = bool(pc > 0.5 and sc > 0.5 and vc > 0.5)
    hybrid = fit([(pilots, PILOT_TRAIN), (seq, idx)], baseline)
    wrong = fit([(pilots, PILOT_TRAIN), (data * WORDS[(state + 1) % 60, mapping], idx)], baseline)
    frequencies = dict(
        pilot=baseline, hybrid=hybrid, wrong_state=wrong, gated=hybrid if qualified else baseline
    )
    arms = {
        name: dict(
            frequency_hz=f,
            held_pilot_nmse=error(pilots, PILOT_TRAIN, f),
            held_sequence_nmse=error(seq, idx, f),
        )
        for name, f in frequencies.items()
    }
    return dict(
        first_symbol=first,
        state=state,
        initial_pilot_coherence=pc,
        selection_coherence=sc,
        verification_coherence=vc,
        qualified=qualified,
        sequence_fit_symbols=len(idx),
        candidates=candidates,
        arms=arms,
    )


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    started = time.monotonic()
    inventory = ROOT / "reports/2026_09_28_signal_clustering/local/inventory.json"
    sources = {str(inventory): digest(inventory)}
    members = json.loads(inventory.read_text())
    streams = []
    for ds, names in [("DS7", ["S02", "S31", "S32"]), ("DS8", ["S13", "S28", "S29"])]:
        for name in names:
            member = next(m for m in members if m["signal"] == name)
            streams.extend(
                (ds, name, rx, Path(s["folder"]), s["row"])
                for rx, s in enumerate(member["streams"])
            )
    for tag in ["middle", "first"]:
        folder = ROOT / f"reports/2026_09_28_sequence_semantics/local/ds9-{tag}-10m"
        ip = folder / "inventory.json"
        sources[str(ip)] = digest(ip)
        streams.extend(
            ("DS9", f"DS9-{tag}", rx, folder, row)
            for rx, row in enumerate(json.loads(ip.read_text())["exports"])
        )
    rows = []
    for ds, name, rx, folder, row in streams:
        path = folder / (row["name"] + ".npy")
        raw = np.load(path)
        assert hashlib.sha256(raw.tobytes()).hexdigest() == row["excerpt_sha256"]
        sources[str(path)] = digest(path)
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
        assert len(pb) >= 2 and len(bins) > 0
        mapping = slots(bins, np.arange(2, 302))
        for frame in range(12):
            ep = epoch + frame * rate / 750
            start = max(0, int(ep) - round(rate * 10e-6))
            stop = start + round(rate * 0.00137)
            assert stop <= len(x)
            sy = demodulate(x[start:stop], rate, ep - start, cfo, center)[1:]
            result = estimate(sy[:, pb] / pilot, sy[:, bins] * template[bins, 1:].T.conj(), mapping)
            result.update(
                dataset=ds,
                signal=name,
                receiver=rx,
                frame=frame,
                session=row["session_id"],
                rate_hz=rate,
            )
            rows.append(result)
        print(ds, name, rx, "complete", flush=True)
    paths = [
        BASE / "study.py",
        BASE / "PROTOCOL.md",
        ROOT / "reports/2026_09_29_sequence_estimator/estimator.py",
        ROOT / "reports/2026_09_29_sequence_estimator/run.py",
        ROOT / "tests/fixtures/qin_edge_pilots_appendix_a_v1.json",
    ]
    paths += [
        ROOT / f"reports/2026_09_27_ds7_header/{name}.py"
        for name in ["tcodes", "analyze", "recover"]
    ]
    refs = (
        ROOT
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement/reference-template"
    )
    paths += [refs / "sssVec.mat", refs / "referenceTemplate.mat"]
    sources.update({str(p): digest(p) for p in paths})
    (BASE / "results.json").write_text(
        json.dumps(
            dict(
                rows=rows,
                input_sha256=sources,
                seconds=time.monotonic() - started,
                python=sys.version,
                numpy=np.__version__,
            ),
            indent=2,
        )
        + "\n"
    )
    print("complete", len(rows), "qualified", sum(r["qualified"] for r in rows))


if __name__ == "__main__":
    main()
