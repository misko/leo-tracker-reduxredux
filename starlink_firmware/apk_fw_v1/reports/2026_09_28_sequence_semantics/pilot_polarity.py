"""Resolve UT symbol polarity using published edge pilots, independently by edge."""

import hashlib
import json
from pathlib import Path

import numpy as np
from scipy.io import loadmat
from scipy.ndimage import uniform_filter1d
from scipy.signal import resample_poly

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[3]
OUT = BASE / "local"


def pilot_reference(deviations, ratios):
    """Two separate eight-pilot phase references; fixed -pi/4 header axis."""
    unit = ratios / np.maximum(abs(ratios), 1e-12)
    means = np.stack([unit[:, :8].mean(axis=1), unit[:, 8:].mean(axis=1)])
    phases = means / np.maximum(abs(means), 1e-12)
    corrected = deviations[None] * phases.conj()[:, :, None] * np.exp(0.25j * np.pi)
    return corrected, means, phases


def main():
    source = ROOT / "docs/research/starlink-literature/local/data/ut-pilots"
    rawpath = source / "exemplar250-257/exemplar250-257.bin"
    raw = np.memmap(rawpath, dtype="<i2", mode="r").reshape(-1, 2)
    reference = source / "supplement/reference-template"
    sss = loadmat(reference / "sssVec.mat")["sssVecFull"].ravel()
    template = np.exp(
        0.5j * np.pi * loadmat(reference / "referenceTemplate.mat")["referenceTemplateRotations"]
    )
    fixture = json.loads((ROOT / "tests/fixtures/qin_edge_pilots_appendix_a_v1.json").read_text())
    pilot_bins = np.r_[488:496, 528:536]
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
    resultpath = ROOT / "reports/2026_09_27_ut_header/local/fullband/results.json"
    result = json.loads(resultpath.read_text())
    bins = np.array(result["subcarrier_indices"])
    freq = np.fft.fftfreq(1024)
    arrays, checks = [], []
    for frame in result["frames"]:
        start = round((frame["metadata_toa_s"] - 10e-6) * 250e6)
        v = raw[start : start + round(1.35e-3 * 250e6)].astype(float)
        x = resample_poly(v[:, 0] + 1j * v[:, 1], 24, 25)
        x *= np.exp(-2j * np.pi * frame["cfo_hz"] * np.arange(len(x)) / 240e6)
        k = round((frame["acquired_toa_s"] - start / 250e6) * 240e6)
        sy = np.array(
            [
                np.fft.fft(x[k + i * 1056 + 16 : k + i * 1056 + 16 + 1024]) / 32
                for i in range(1, 302)
            ]
        )
        h = np.zeros(1024, complex)
        loaded = abs(sss) > 0
        h[loaded] = sy[0, loaded] / sss[loaded]
        h = uniform_filter1d(h.real, 9, mode="wrap") + 1j * uniform_filter1d(h.imag, 9, mode="wrap")
        y = sy[1:] / np.where(abs(h) > 0, h, 1)
        delays = np.array([s["delay_samples"] for s in frame["symbols"]])
        y *= np.exp(-2j * np.pi * delays[:, None] * freq)
        ratios = y[:, pilot_bins] / pilot
        deviations = y[:, bins] * template[bins, 1:].T.conj()
        corrected, means, phases = pilot_reference(deviations, ratios)
        arrays.append(corrected)
        checks.append(
            dict(
                frame=frame["frame_id"],
                edge_coherence=abs(means).tolist(),
                edge_phase_agreement=(phases[0] * phases[1].conj()).real.tolist(),
                header_sign_agreement=np.mean(
                    np.sign(corrected[0, :6].real) == np.sign(corrected[1, :6].real), axis=1
                ).tolist(),
                header_axis_real=[
                    np.mean((z[:6] / np.maximum(abs(z[:6]), 1e-12)) ** 2, axis=1).real.tolist()
                    for z in corrected
                ],
            )
        )
    np.savez_compressed(OUT / "pilot_polarity.npz", deviations=np.array(arrays), bins=bins)
    output = dict(
        checks=checks,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                rawpath,
                resultpath,
                ROOT / "tests/fixtures/qin_edge_pilots_appendix_a_v1.json",
            ]
        },
        limitation="Each edge fits phase independently, but both share SSS channel and blind "
        "delay estimates; no FEC/CRC verification.",
    )
    (OUT / "pilot_polarity.json").write_text(json.dumps(output, indent=2) + "\n")
    for row in checks:
        print(
            row["frame"],
            "header axis",
            np.round(row["header_axis_real"], 3).tolist(),
            "edge coherence",
            np.round(np.array(row["edge_coherence"])[:, :6], 3).tolist(),
            "sign agreement",
            np.round(row["header_sign_agreement"], 3).tolist(),
        )


if __name__ == "__main__":
    main()
