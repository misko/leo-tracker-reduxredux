"""Compare lower-edge mapping hypotheses using UT raw IQ only."""

import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports/2026_09_27_ds7_header"))
import tcodes  # noqa: E402


def main():
    bins, _, center = tcodes.geometry("lower")
    sss, template, pilot = tcodes.references("lower")
    raw = np.memmap(
        ROOT / "docs/research/starlink-literature/local/data/ut-pilots/"
        "exemplar250-257/exemplar250-257.bin",
        dtype="<i2",
        mode="r",
    ).reshape(-1, 2)
    frames = json.loads((ROOT / "reports/2026_09_27_ut_header/local/results.json").read_text())[
        "frames"
    ]
    models = [
        (
            "simple",
            lambda b, s: (tcodes.compact_indices(b)[None, :] - 16 * np.asarray(s)[:, None]) % 60,
        )
    ]
    for phase in range(0, 60, 4):
        models.append(
            (
                f"finite-{phase}",
                lambda b, s, phase=phase: (
                    (
                        (
                            tcodes.compact_indices(b)[None, :]
                            - (16 * np.asarray(s)[:, None] + phase) % 60
                        )
                        % 1004
                    )
                    % 60
                ),
            )
        )
    output = []
    for frame in frames:
        start = round((frame["acquired_toa_s"] - 10e-6) * 250e6)
        v = raw[start : start + 340000].astype(float)
        x = (v[:, 0] + 1j * v[:, 1]) * np.exp(
            -2j * np.pi * (center + frame["cfo_hz"]) * np.arange(len(v)) / 250e6
        )
        sy = tcodes.demodulate(tcodes.resample_poly(x, 1, 25), 1e7, 100, 0, center)
        sy, diagnostic = tcodes.pilot_calibrate(sy, pilot, edge="lower")
        z = sy[1:, bins] / (sy[0, bins] / sss[bins]) * template[bins, 1:].T.conj()
        trials = []
        for name, mapping in models:
            tcodes.slots = mapping
            first, score, _ = tcodes.select_window(z, bins)
            code, _, _ = tcodes.fit_code(
                z[first - 2 : first + 62], mapping(bins, np.arange(first, first + 64))
            )
            trials.append(dict(model=name, score=score, code=tcodes.bit_word(code)))
        output.append(dict(frame=frame["frame_id"], diagnostic=diagnostic, trials=trials))
        print(frame["frame_id"], sorted(trials, key=lambda r: -r["score"])[:2], flush=True)
    (Path(__file__).parent / "local/ut-lower-models.json").write_text(
        json.dumps(output, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()
