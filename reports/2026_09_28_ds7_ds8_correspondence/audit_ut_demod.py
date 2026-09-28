"""Validate known pilots at both edges of the UT raw signal, without T-code assumptions."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent / "local"
sys.path.insert(0, str(ROOT / "reports/2026_09_27_ds7_header"))
import tcodes  # noqa: E402


def main():
    path = (
        ROOT / "docs/research/starlink-literature/local/data/ut-pilots/"
        "exemplar250-257/exemplar250-257.bin"
    )
    raw = np.memmap(path, dtype="<i2", mode="r").reshape(-1, 2)
    frames = json.loads((ROOT / "reports/2026_09_27_ut_header/local/results.json").read_text())[
        "frames"
    ]
    rows = []
    for f in frames:
        start = round((f["acquired_toa_s"] - 10e-6) * 250e6)
        v = raw[start : start + 340000].astype(float)
        x = (v[:, 0] + 1j * v[:, 1]) * np.exp(-2j * np.pi * f["cfo_hz"] * np.arange(len(v)) / 250e6)
        for edge in ("upper", "lower"):
            bins, pilot_bins, center = tcodes.geometry(edge)
            sss, template, pilot = tcodes.references(edge)
            shifted = x * np.exp(-2j * np.pi * center * np.arange(len(x)) / 250e6)
            sy = tcodes.demodulate(tcodes.resample_poly(shifted, 1, 25), 1e7, 100, 0, center)
            y, diagnostic = tcodes.pilot_calibrate(sy, pilot, edge=edge)
            header = y[1:9, bins] / (y[0, bins] / sss[bins]) * template[bins, 1:9].T.conj()
            unit = header / np.maximum(abs(header), 1e-20)
            held = y[1:21, pilot_bins] / pilot[:20]
            wrong = [
                float(
                    abs((y[1:21, pilot_bins] / np.roll(pilot, i, axis=0)[:20]).mean())
                    / np.sqrt(np.mean(abs(held) ** 2))
                )
                for i in range(21, 121)
            ]
            rows.append(
                dict(
                    frame=f["frame_id"],
                    edge=edge,
                    **diagnostic,
                    heldout_wrong_sequence_max=max(wrong),
                    header_bpsk_concentration=float(np.mean(abs((unit**2).mean(axis=1)))),
                    long_tcode_block_assumed=False,
                )
            )
    result = dict(
        raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        rows=rows,
        method="Fit pilot symbols 22..301; validate known pilots 2..21; "
        "100 shifted pilot-sequence controls. No T-code positive-control assumption.",
    )
    (OUT / "raw-ut-demodulation-check.json").write_text(json.dumps(result, indent=2) + "\n")
    for edge in ("upper", "lower"):
        r = [x for x in rows if x["edge"] == edge]
        print(
            edge,
            "held pilot correlation",
            min(x["pilot_holdout_coherence"] for x in r),
            max(x["pilot_holdout_coherence"] for x in r),
            "max wrong",
            max(x["heldout_wrong_sequence_max"] for x in r),
        )


if __name__ == "__main__":
    main()
