"""Exploratory narrowband header assay; cached-pilot aided, not blind acquisition."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "local"
FS = 240e6
SPACING = FS / 1024
PILOT_CENTER = 491.5 * SPACING


def demodulate(x, fs, epoch, cfo, center=PILOT_CENTER):
    """Interpolate captured band only; shift onto native OFDM grid, then FFT."""
    x = x * np.exp(-2j * np.pi * cfo * np.arange(len(x)) / fs)
    ratio = int(round(FS / fs))
    assert ratio * fs == FS
    y = resample_poly(x, ratio, 1)
    y *= np.exp(2j * np.pi * center * np.arange(len(y)) / FS)
    starts = np.rint(epoch * ratio + np.arange(1, 302) * 1056 + 16).astype(int)
    assert starts[0] >= 0 and starts[-1] + 1024 <= len(y)
    return np.fft.fft(y[starts[:, None] + np.arange(1024)], axis=1)


def score(symbols, sss, template, bins):
    # Per-subcarrier SSS equalization. No fitting against the header template.
    h = symbols[0, bins] / sss[bins]
    z = symbols[1:, bins] / h
    z /= np.maximum(abs(z), 1e-20)
    tr = template[bins, 1:].T
    exact = abs(np.mean((z * tr.conj()) ** 2, axis=1))
    controls = np.array(
        [abs(np.mean((z * np.roll(tr, n, axis=0).conj()) ** 2, axis=1)) for n in range(11, 111)]
    )
    return exact, controls


def main():
    refs = (
        ROOT
        / "docs/research/starlink-literature/local/data/ut-pilots/supplement/reference-template"
    )
    sss = loadmat(refs / "sssVec.mat")["sssVecFull"].ravel()
    rotations = loadmat(refs / "referenceTemplate.mat")["referenceTemplateRotations"]
    template = np.exp(0.5j * np.pi * rotations)
    fixture = json.loads((ROOT / "tests/fixtures/qin_edge_pilots_appendix_a_v1.json").read_text())
    pilot = np.array(
        [
            [
                np.exp(
                    0.5j * np.pi * ((int(fixture["sequences"][str(k)], 16) >> (2 * (299 - s))) & 3)
                )
                for k in range(488, 496)
            ]
            for s in range(300)
        ]
    )
    # Stay inside conservative +/- 3.8 MHz around pilot center, excluding pilots.
    bins = np.r_[476:488, 496:508]
    inventory = json.loads((OUT / "inventory.json").read_text())
    results, arrays = [], {}
    for row in inventory["exports"]:
        raw = np.load(OUT / (row["name"] + ".npy"))
        assert hashlib.sha256(raw.tobytes()).hexdigest() == row["excerpt_sha256"]
        x = raw[:, 0].astype(float) + 1j * raw[:, 1]
        c = row["candidate"]
        centered = x * np.exp(
            -2j * np.pi * c["fractional_tracking_cfo_hz"] * np.arange(len(x)) / 10e6
        )
        np.save(
            OUT / (row["name"] + "-pilot-band-2Msps.npy"),
            resample_poly(centered, 1, 5).astype(np.complex64),
        )
        epoch = c["integer_epoch_sample"] + c["fractional_epoch_offset_samples"]
        # Every complete predicted frame in the fixed 20 ms excerpt. Select by
        # pilot rank-one coherence only, without consulting the header scores.
        frame_trials = []
        for frame in range(15):
            ep = epoch + frame * 10e6 / 750
            start = max(0, int(ep) - 100)
            if start + 13600 > len(x):
                continue
            sy = demodulate(
                x[start : start + 13600], 10e6, ep - start, c["fractional_tracking_cfo_hz"]
            )
            sv = np.linalg.svd(sy[1:, 488:496] / pilot, compute_uv=False)
            coherence = float(sv[0] ** 2 / np.sum(sv**2))
            frame_trials.append((coherence, frame, sy))
        coherence, frame, symbols = max(frame_trials, key=lambda trial: trial[0])
        # Common phase per symbol is free; check relative phases across the eight
        # pilots, calibrating their static channel on the SSS only.
        ph = symbols[0, 488:496] / sss[488:496]
        p = symbols[1:, 488:496] / ph / pilot
        p /= np.maximum(abs(p), 1e-20)
        pilot_exact = abs(np.mean(p, axis=1))
        exact, controls = score(symbols, sss, template, bins)
        result = dict(
            name=row["name"],
            bins=bins.tolist(),
            frame=frame,
            frame_epoch_sample=epoch + frame * 10e6 / 750,
            pilot_rank1_fraction=coherence,
            frame_pilot_rank1_fractions=[v[0] for v in frame_trials],
            pilot_mean_coherence=float(pilot_exact.mean()),
            header_first8_mean=float(exact[:8].mean()),
            later_mean=float(exact[20:].mean()),
            first20_scores=exact[:20].tolist(),
            control_first8_means=controls[:, :8].mean(axis=1).tolist(),
        )
        result["all_frame_header_scores"] = [
            dict(frame=f, first8_mean=float(score(sy, sss, template, bins)[0][:8].mean()))
            for _, f, sy in frame_trials
        ]
        results.append(result)
        arrays[row["name"]] = symbols[:, bins]
        print(json.dumps(result))
    np.savez_compressed(OUT / "demodulated.npz", **arrays)
    (OUT / "results.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    main()
