"""Controlled bandwidth-loss assay; retains high-rate acquisition/calibration aids.

This is not native-rate or blind-acquisition qualification. Truth words are
compared only after demodulation; unobserved code positions stay unknown.
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "local/rate-validation"
sys.path.insert(0, str(ROOT / "reports/2026_09_27_ds7_header"))
from tcodes import (  # noqa: E402
    bit_word,
    demodulate,
    fit_code,
    geometry,
    pilot_calibrate,
    references,
    resample_poly,
    score_code,
    slots,
)


def retained_bins(edge, rate):
    bins, _, center = geometry(edge)
    frequencies = np.fft.fftfreq(1024, 1 / 240e6)[bins]
    return bins[abs(frequencies - center) <= 0.45 * rate]


def main():
    OUT.mkdir(exist_ok=True)
    folders = [
        ROOT / "reports/2026_09_27_ds7_header/local/best-upper",
        Path(__file__).parent / "local/repeat-4",
    ]
    results = []
    for folder in folders:
        inventory = json.loads((folder / "inventory.json").read_text())
        records = json.loads((folder / "recovery.json").read_text())
        truth = json.loads((folder / "tcodes.json").read_text())["results"][:8]
        archive = np.load(folder / "recovery-soft-symbols.npz")
        edge = inventory["exports"][0]["probe"]["edge"]
        fullbins, _, center = geometry(edge)
        _, template, pilot = references(edge)
        streams = []
        for e in inventory["exports"]:
            raw = np.load(folder / (e["name"] + ".npy"))
            assert hashlib.sha256(raw.tobytes()).hexdigest() == e["excerpt_sha256"]
            streams.append(raw[:, 0].astype(float) + 1j * raw[:, 1])
        for rate, up, down in [(10000000, 1, 1), (7500000, 3, 4), (5000000, 1, 2), (2500000, 1, 4)]:
            bins = retained_bins(edge, rate)
            indices = np.flatnonzero(np.isin(fullbins, bins))
            for t in truth:
                if not t["repeated_code_candidate"]:
                    continue
                frame = t["frame"]
                observations = []
                for e, record, x in zip(inventory["exports"], records, streams, strict=True):
                    ep = record["corrected_frame_epochs_samples"][frame]
                    start = int(ep) - 100
                    cut = x[start : start + 13600].copy()
                    cut *= np.exp(
                        -2j
                        * np.pi
                        * e["candidate"]["fractional_tracking_cfo_hz"]
                        * np.arange(len(cut))
                        / 1e7
                    )
                    narrow = resample_poly(cut, up, down, window=("kaiser", 8.6))
                    sy = demodulate(narrow, rate, (ep - start) * rate / 1e7, 0, center)
                    y, _ = pilot_calibrate(
                        sy, pilot, record["diagnostics"][frame]["phase_slope"], edge
                    )
                    h = archive[e["name"] + "_sss_channel"][frame][indices]
                    z = y[1:, bins] / h * template[bins, 1:].T.conj()
                    first = t["first_symbol"]
                    observations.append(z[first - 2 : first + 62])
                mapping = slots(bins, np.arange(first, first + 64))
                a, _, count = fit_code(observations[0], mapping)
                b, _, _ = fit_code(observations[1], mapping)
                known = count > 0
                expected = np.array([1 if c == "1" else -1 for c in t["combined_word"]])
                results.append(
                    dict(
                        group=folder.name,
                        edge=edge,
                        frame=frame,
                        rate_hz=rate,
                        bins=bins.tolist(),
                        observed_bits=int(known.sum()),
                        rx0_errors=int(np.sum(a[known] != expected[known])),
                        rx1_errors=int(np.sum(b[known] != expected[known])),
                        rx_disagreements=int(np.sum(a[known] != b[known])),
                        rx1_correlation=score_code(observations[1], mapping, a),
                        rx0_word=bit_word(a),
                        rx1_word=bit_word(b),
                    )
                )
            rows = [r for r in results if r["group"] == folder.name and r["rate_hz"] == rate]
            print(
                folder.name,
                rate,
                len(rows),
                "frames; observed bits",
                len(set(mapping.ravel())),
                "RX errors",
                sum(r["rx0_errors"] + r["rx1_errors"] for r in rows),
                flush=True,
            )
    (OUT / "controlled-results.json").write_text(
        json.dumps(
            dict(
                scope="Paired software anti-alias/downsample from 10 MS/s; pilot-centered; "
                "45%-of-rate conservative bin support; Kaiser 8.6 resampling. "
                "High-rate epochs, CFO, phase-slope and SSS calibration retained. "
                "Reference-selected windows; no native-rate validation claim.",
                results=results,
            ),
            indent=2,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
