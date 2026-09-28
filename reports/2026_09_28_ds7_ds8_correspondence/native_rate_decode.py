"""Native-rate pilot/SSS aided assay; no imported high-rate timing or codewords."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import minimize_scalar

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "local/rate-validation/native"
sys.path.insert(0, str(ROOT / "reports/2026_09_27_ds7_header"))
from tcodes import (  # noqa: E402
    bit_word,
    demodulate,
    fit_code,
    geometry,
    references,
    score_code,
    select_window,
    slots,
)

TS = 4.4e-6


def supported_bins(bins, center, rate, cfo):
    """Keep original captured frequencies, not frequencies after digital mixing."""
    frequency = np.fft.fftfreq(1024, 1 / 240e6)[bins] - center + cfo
    return np.asarray(bins)[abs(frequency) <= 0.45 * rate]


def calibrate(sy, pilot, pilot_bins, fitted_slope=None):
    z = sy[1:, pilot_bins] / pilot
    t = np.arange(300) * TS
    v = z.mean(axis=1)
    nominal = np.fft.fftfreq(8192, TS)[np.argmax(abs(np.fft.fft(v[20:], n=8192)))]
    freq = minimize_scalar(
        lambda f: -abs(np.mean(v[20:] * np.exp(-2j * np.pi * f * t[20:]))),
        bounds=(nominal - 1000, nominal + 1000),
        method="bounded",
    ).x
    h = np.mean(z[20:] * np.exp(-2j * np.pi * freq * t[20:])[:, None], axis=0)
    pivot = pilot_bins.mean()
    slope, intercept = np.polyfit(pilot_bins - pivot, np.unwrap(np.angle(h)), 1)
    if fitted_slope is not None:
        slope = fitted_slope
        intercept = np.angle(np.mean(h * np.exp(-1j * slope * (pilot_bins - pivot))))
    response = abs(h).mean() * np.exp(1j * (slope * (np.arange(1024) - pivot) + intercept))
    y = sy / response * np.exp(-2j * np.pi * freq * (np.arange(301) - 1) * TS)[:, None]
    held = y[1:21, pilot_bins] / pilot[:20]
    return y, dict(
        phase_slope=float(slope),
        held_pilot_coherence=float(abs(held.mean()) / np.sqrt(np.mean(abs(held) ** 2))),
    )


def recover(row, folder, frame_limit=24):
    rate = row["sample_rate_hz"]
    edge = row["probe"]["edge"]
    bins, allpilots, center = geometry(edge)
    sss, template, pilot = references(edge)
    c = row["candidate"]
    cfo = c["fractional_tracking_cfo_hz"]
    bins = supported_bins(bins, center, rate, cfo)
    pb = supported_bins(allpilots, center, rate, cfo)
    pilot = pilot[:, np.isin(allpilots, pb)]
    assert len(pb) >= 2 and len(bins) > 0
    raw = np.load(folder / (row["name"] + ".npy"))
    assert hashlib.sha256(raw.tobytes()).hexdigest() == row["excerpt_sha256"]
    x = raw[:, 0].astype(float) + 1j * raw[:, 1]
    epoch = c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"]
    # Keep a 10-us end guard for pilot-derived retiming. The default preserves
    # the original 24-frame assay; larger limits enable bounded excerpt audits.
    available = int(np.floor((len(x) - epoch - rate * 0.00138) * 750 / rate)) + 1
    nframes = min(frame_limit, available)
    if nframes < 4:
        raise ValueError("At least four complete frames are required for calibration/evaluation")
    epochs = epoch + np.arange(nframes) * rate / 750

    def demod(ep):
        start = max(0, int(ep) - round(rate * 10e-6))
        stop = start + round(rate * 0.00137)
        assert stop <= len(x)
        return demodulate(x[start:stop], rate, ep - start, cfo, center)

    original = [demod(ep) for ep in epochs]
    slopes = [calibrate(sy, pilot, pb)[1]["phase_slope"] for sy in original]
    drift = np.polyfit(np.arange(nframes), slopes, 1)[0]
    epochs -= drift * np.arange(nframes) * 1024 / (2 * np.pi * (240e6 / rate))
    retimed = [demod(ep) for ep in epochs]
    slopes = [calibrate(sy, pilot, pb)[1]["phase_slope"] for sy in retimed]
    fit = np.polyval(np.polyfit(np.arange(nframes), slopes, 1), np.arange(nframes))
    calibrated = [calibrate(sy, pilot, pb, slope) for sy, slope in zip(retimed, fit, strict=True)]
    frames = np.array([sy[:, bins] for sy, _ in calibrated])
    h = frames[:, 0] / sss[bins]
    # Random whole frames reserved for SSS channel estimation; evaluation frames
    # never supply their own SSS to their channel estimate. Same split both RX.
    train = np.sort(np.random.default_rng(20260928).choice(nframes, nframes // 2, replace=False))
    evaluation = np.setdiff1d(np.arange(nframes), train)
    design = np.c_[np.ones(len(bins)), (bins - pb.mean()) / 16]
    channel = design @ np.linalg.lstsq(design, h[train].mean(axis=0), rcond=None)[0]
    z = frames[:, 1:] / channel * template[bins, 1:].T.conj()
    metadata = dict(
        name=row["name"],
        bins=bins.tolist(),
        pilot_bins=pb.tolist(),
        sample_clock_ppm=float(-drift / (2 * np.pi * 234375) * 750e6),
        calibration_frames=train.tolist(),
        evaluation_frames=evaluation.tolist(),
        diagnostics=[d for _, d in calibrated],
    )
    return bins, z, metadata


def main():
    summary = []
    for path in sorted(OUT.glob("*/inventory.json")):
        inventory = json.loads(path.read_text())
        streams = [recover(row, path.parent) for row in inventory["exports"]]
        b0, z0, d0 = streams[0]
        b1, z1, d1 = streams[1]
        results = []
        for frame in d0["evaluation_frames"]:
            first, selection_score, _ = select_window(z0[frame], b0)
            symbols = np.arange(first, first + 64)
            a, b = z0[frame, symbols - 2], z1[frame, symbols - 2]
            m0, m1 = slots(b0, symbols), slots(b1, symbols)
            code0, _, count0 = fit_code(a, m0)
            code1, _, count1 = fit_code(b, m1)
            shared = (count0 > 0) & (count1 > 0)
            # RX1 test uses only positions actually learned on RX0.
            mask = shared[m1]
            held = score_code(b[mask], m1[mask], code0) if mask.any() else 0
            controls = []
            rng = np.random.default_rng(701 + frame)
            for _ in range(1000):
                wrong = code0.copy()
                wrong[shared] = rng.permutation(code0[shared])
                controls.append(score_code(b[mask], m1[mask], wrong) if mask.any() else 0)
            pilot_ok = min(d["diagnostics"][frame]["held_pilot_coherence"] for d in [d0, d1]) > 0.5
            agreement = bool(shared.any() and np.array_equal(code0[shared], code1[shared]))
            passed = bool(
                pilot_ok
                and selection_score > 0.25
                and held > 0.25
                and held > max(controls)
                and agreement
            )
            results.append(
                dict(
                    frame=frame,
                    first_symbol=first,
                    rx0_word=bit_word(code0),
                    rx1_word=bit_word(code1),
                    rx0_observed=int((count0 > 0).sum()),
                    rx1_observed=int((count1 > 0).sum()),
                    shared_slots=int(shared.sum()),
                    shared_errors=int(np.sum(code0[shared] != code1[shared])),
                    rx0_selection_score=selection_score,
                    rx1_held_correlation=held,
                    wrong_code_max=max(controls),
                    held_pilots_pass=bool(pilot_ok),
                    repeated_pattern_candidate=passed,
                    full_word_candidate=bool(passed and shared.all()),
                )
            )
        result = dict(
            group=path.parent.name,
            rate_hz=inventory["exports"][0]["sample_rate_hz"],
            receivers=[d0, d1],
            results=results,
        )
        (path.parent / "native-results.json").write_text(json.dumps(result, indent=2) + "\n")
        summary.append(
            dict(
                group=result["group"],
                rate_hz=result["rate_hz"],
                frames=len(results),
                full_words=sum(r["full_word_candidate"] for r in results),
                partial_or_full=sum(r["repeated_pattern_candidate"] for r in results),
                shared_slots=results[0]["shared_slots"],
                receiver_slots=[results[0]["rx0_observed"], results[0]["rx1_observed"]],
            )
        )
        print(summary[-1], flush=True)
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")


if __name__ == "__main__":
    main()
