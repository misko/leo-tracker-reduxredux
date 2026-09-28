"""Pilot-aided post-SSS recovery with independent, multi-frame SSS calibration.

Fits only published pilots and SSS, never the header template. All outputs are
soft observations until independently qualified. No payload/identity decoding.
"""

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from analyze import OUT, ROOT, demodulate
from scipy.io import loadmat
from scipy.optimize import minimize_scalar

TS = 4.4e-6
BINS = np.r_[476:488, 496:508]


def geometry(edge):
    if edge == "upper":
        return BINS, np.arange(488, 496), 491.5 * 234375
    if edge == "lower":
        return np.r_[516:528, 536:548], np.arange(528, 536), -492.5 * 234375
    raise ValueError(f"Unsupported edge: {edge}")


def references(edge="upper"):
    _, pilot_bins, _ = geometry(edge)
    refs = (
        ROOT
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement/reference-template"
    )
    sss = loadmat(refs / "sssVec.mat")["sssVecFull"].ravel()
    template = np.exp(
        0.5j * np.pi * loadmat(refs / "referenceTemplate.mat")["referenceTemplateRotations"]
    )
    fixture = json.loads((ROOT / "tests/fixtures/qin_edge_pilots_appendix_a_v1.json").read_text())
    pilot = np.array(
        [
            [
                np.exp(
                    0.5j * np.pi * ((int(fixture["sequences"][str(k)], 16) >> (2 * (299 - s))) & 3)
                )
                for k in pilot_bins
            ]
            for s in range(300)
        ]
    )
    return sss, template, pilot


def pilot_calibrate(symbols, pilot, shared_slope=None, edge="upper"):
    """Fit phase on symbols 22–301; reserve symbols 2–21 for validation."""
    _, pilot_bins, _ = geometry(edge)
    pivot = pilot_bins.mean()
    z = symbols[1:, pilot_bins] / pilot
    t = np.arange(300) * TS
    # Upconversion onto native FFT grid adds this deterministic symbol-phase
    # increment. Fit remaining frequency locally using known pilots only.
    v = z.mean(axis=1)
    spectrum = np.fft.fft(v[20:], n=8192)
    nominal = np.fft.fftfreq(8192, TS)[np.argmax(abs(spectrum))]
    freq = minimize_scalar(
        lambda f: -abs(np.mean(v[20:] * np.exp(-2j * np.pi * f * t[20:]))),
        bounds=(nominal - 1000, nominal + 1000),
        method="bounded",
    ).x
    h = np.mean(z[20:] * np.exp(-2j * np.pi * freq * t[20:])[:, None], axis=0)
    slope, intercept = np.polyfit(pilot_bins - pivot, np.unwrap(np.angle(h)), 1)
    if shared_slope is not None:
        slope = shared_slope
        intercept = np.angle(np.mean(h * np.exp(-1j * slope * (pilot_bins - pivot))))
    response = np.mean(abs(h)) * np.exp(1j * (slope * (np.arange(1024) - pivot) + intercept))
    corrected = symbols / response * np.exp(-2j * np.pi * freq * (np.arange(301) - 1) * TS)[:, None]
    held = corrected[1:21, pilot_bins] / pilot[:20]
    return corrected, dict(
        frequency_hz=float(freq),
        phase_slope=float(slope),
        pilot_holdout_coherence=float(abs(held.mean()) / np.sqrt(np.mean(abs(held) ** 2))),
        pilot_holdout_evm=float(np.sqrt(np.mean(abs(held - 1) ** 2))),
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()
    out = args.out
    exports = json.loads((out / "inventory.json").read_text())["exports"]
    edges = {row["probe"]["edge"] for row in exports}
    assert len(edges) == 1, "Use a separate output directory for each edge"
    edge = edges.pop()
    bins, pilot_bins, center = geometry(edge)
    sss, template, pilot = references(edge)
    rows, arrays = [], {}
    for row in exports:
        raw = np.load(out / (row["name"] + ".npy"))
        assert row["sample_rate_hz"] == 10000000
        assert hashlib.sha256(raw.tobytes()).hexdigest() == row["excerpt_sha256"]
        x = raw[:, 0].astype(float) + 1j * raw[:, 1]
        c = row["candidate"]
        epoch = c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"]
        frames, diagnostics, raw_frames = [], [], []
        for frame in range(min(91, int(len(x) / 1e7 * 750) + 1)):
            ep = epoch + frame * 1e7 / 750
            start = int(ep) - 100
            if start + 13600 > len(x):
                continue
            sy = demodulate(
                x[start : start + 13600], 1e7, ep - start, c["fractional_tracking_cfo_hz"], center
            )
            corrected, diag = pilot_calibrate(sy, pilot, edge=edge)
            raw_frames.append(sy)
            frames.append(corrected[:, bins])
            diagnostics.append(diag)
        slope_fit = np.polyfit(
            np.arange(len(diagnostics)), [d["phase_slope"] for d in diagnostics], 1
        )
        # Put later windows back inside the CP. Constant timing is deliberately
        # left at the acquired anchor; only pilot-measured drift is corrected.
        epoch_corrections = -slope_fit[0] * np.arange(len(raw_frames)) * 1024 / (2 * np.pi * 24)
        retimed = []
        retimed_diagnostics = []
        for frame, delta in enumerate(epoch_corrections):
            ep = epoch + frame * 1e7 / 750 + delta
            start = int(ep) - 100
            sy = demodulate(
                x[start : start + 13600], 1e7, ep - start, c["fractional_tracking_cfo_hz"], center
            )
            retimed.append(sy)
            retimed_diagnostics.append(pilot_calibrate(sy, pilot, edge=edge)[1])
        raw_frames = retimed
        residual_fit = np.polyfit(
            np.arange(len(raw_frames)), [d["phase_slope"] for d in retimed_diagnostics], 1
        )
        fitted_slopes = np.polyval(residual_fit, np.arange(len(diagnostics)))
        calibrated = [
            pilot_calibrate(sy, pilot, float(slope), edge=edge)
            for sy, slope in zip(raw_frames, fitted_slopes, strict=True)
        ]
        frames = np.array([sy[:, bins] for sy, _ in calibrated])
        diagnostics = [diag for _, diag in calibrated]
        # Channel estimate excludes the target frame's own SSS. The post-SSS
        # data never enters the calibration fit.
        h = frames[:, 0] / sss[bins]
        channel_noisy = (h.sum(axis=0)[None, :] - h) / (len(h) - 1)
        # A smooth complex-linear response avoids dividing by noisy individual
        # SSS bins. Header observations are still excluded from the fit.
        design = np.c_[np.ones(len(bins)), (bins - pilot_bins.mean()) / 16]
        channel = np.array(
            [design @ np.linalg.lstsq(design, hi, rcond=None)[0] for hi in channel_noisy]
        )
        recovered = frames[:, 1:21] / channel[:, None, :]
        deviations = recovered * template[bins, 1:21].T.conj()
        unit = deviations / np.maximum(abs(deviations), 1e-20)
        concentration = abs(np.mean(unit**2, axis=(0, 2)))
        wrong = []
        for shift in range(11, 111):
            d = recovered * template[bins, 1 + shift : 21 + shift].T.conj()
            wrong.append(abs(np.mean((d / np.maximum(abs(d), 1e-20)) ** 2, axis=(0, 2))))
        wrong = np.array(wrong)
        result = dict(
            name=row["name"],
            edge=edge,
            subcarrier_indices=bins.tolist(),
            frames=len(frames),
            diagnostics=diagnostics,
            phase_slope_change_per_frame=float(slope_fit[0]),
            inferred_sample_clock_ppm=float(-slope_fit[0] / (2 * np.pi * 234375) * (750 * 1e6)),
            epoch_corrections_samples=epoch_corrections.tolist(),
            corrected_frame_epochs_samples=(
                epoch + np.arange(len(frames)) * 1e7 / 750 + epoch_corrections
            ).tolist(),
            residual_phase_slope_change_per_frame=float(residual_fit[0]),
            sss_coherence=float(abs(h.mean()) / np.sqrt(np.mean(abs(h) ** 2))),
            header_symbol_concentration=concentration.tolist(),
            control_symbol_max=wrong.max(axis=0).tolist(),
            mean_first8=float(concentration[:8].mean()),
            control_first8_max=float(wrong[:, :8].mean(axis=1).max()),
        )
        rows.append(result)
        arrays[row["name"] + "_symbols"] = recovered
        arrays[row["name"] + "_deviations"] = deviations
        arrays[row["name"] + "_sss_channel"] = channel
        arrays[row["name"] + "_sss_observations"] = h
        arrays[row["name"] + "_pilot_corrected"] = frames[:, :21]
        print(json.dumps(result))
    (out / "recovery.json").write_text(json.dumps(rows, indent=2) + "\n")
    np.savez_compressed(out / "recovery-soft-symbols.npz", bins=bins, **arrays)


if __name__ == "__main__":
    main()
