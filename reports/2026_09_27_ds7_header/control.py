"""UT positive control after real filtering/decimation to a 10 MS/s edge slice.

Uses the previous full-band UT timing/CFO solution: tests demodulation, not
independent narrowband acquisition.
"""

import argparse
import json

import numpy as np
from analyze import OUT, ROOT, demodulate, score
from recover import geometry
from scipy.io import loadmat
from scipy.signal import resample_poly


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--edge", choices=["upper", "lower"], default="upper")
    args = parser.parse_args()
    bins, _, center = geometry(args.edge)
    source = ROOT / "docs/research/starlink-literature/local/data/ut-pilots"
    refs = source / "supplement/reference-template"
    sss = loadmat(refs / "sssVec.mat")["sssVecFull"].ravel()
    template = np.exp(
        0.5j * np.pi * loadmat(refs / "referenceTemplate.mat")["referenceTemplateRotations"]
    )
    raw = np.memmap(source / "exemplar250-257/exemplar250-257.bin", dtype="<i2", mode="r").reshape(
        -1, 2
    )
    frames = json.loads((ROOT / "reports/2026_09_27_ut_header/local/results.json").read_text())[
        "frames"
    ]
    rows = []
    for frame in frames:
        start = round((frame["acquired_toa_s"] - 10e-6) * 250e6)
        v = raw[start : start + round(1.36e-3 * 250e6)].astype(float)
        x = v[:, 0] + 1j * v[:, 1]
        # Mix at original sample rate BEFORE filtering/decimation.
        x *= np.exp(-2j * np.pi * (center + frame["cfo_hz"]) * np.arange(len(x)) / 250e6)
        narrow = resample_poly(x, 1, 25)
        sy = demodulate(narrow, 1e7, 100, 0, center)
        exact, controls = score(sy, sss, template, bins)
        rows.append(
            dict(
                frame_id=frame["frame_id"],
                first8_mean=float(exact[:8].mean()),
                control_max_first8=float(controls[:, :8].mean(axis=1).max()),
                first20=exact[:20].tolist(),
            )
        )
    name = "ut-control.json" if args.edge == "upper" else "ut-lower-control.json"
    (OUT / name).write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps(rows))


if __name__ == "__main__":
    main()
