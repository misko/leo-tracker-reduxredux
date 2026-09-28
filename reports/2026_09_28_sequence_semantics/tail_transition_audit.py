"""Check whether tail signs precede the real-axis transition in QAM symbols."""

import hashlib
import json
from pathlib import Path

import numpy as np
from region_phase_audit import WORDS
from scipy.io import loadmat

BASE = Path(__file__).parent


def rectangle_boundary(values, target, allowed_errors=2):
    """Locate magnitude-pair membership without consulting signs or phase."""
    coordinates = np.c_[abs(values.real), abs(values.imag)]
    qualified = np.max(abs(coordinates - target), axis=1) < 0.01
    counts = np.convolve(qualified.astype(int), np.ones(240, dtype=int), "valid")
    candidates = np.flatnonzero(counts >= 240 - allowed_errors)
    return int(candidates[0]) if candidates.size else None


def sign_agreement(values, prediction):
    observed = np.where(values.real >= 0, 1, -1)
    valid = np.isfinite(values) & (abs(values.real) > 0.05)
    a, b = observed[valid], prediction[valid]
    return dict(
        support=int(valid.sum()),
        errors=int((a != b).sum()),
        agreement=float(np.mean(a == b)),
        marginal_agreement=float(
            np.mean(a == 1) * np.mean(b == 1) + np.mean(a == -1) * np.mean(b == -1)
        ),
    )


def main():
    source = BASE / "local/full-reference-0-12.npz"
    boundary_path = BASE / "local/tail_axis_boundary.json"
    phase_path = BASE / "local/region_phase_audit.json"
    template_path = (
        BASE.parents[1]
        / "docs/research/starlink-literature/local/data/ut-pilots"
        / "supplement/reference-template/referenceTemplate.mat"
    )
    bins = np.array(
        [
            k
            for k in np.argsort(np.fft.fftfreq(1024))
            if 2 <= k < 1022 and k not in range(488, 496) and k not in range(528, 536)
        ]
    )
    archive = np.load(source)
    template = loadmat(template_path)["referenceTemplateRotations"]
    z = archive["symbols"][:, 1:][:, :, bins] * np.exp(-0.5j * np.pi * template[bins, 1:].T)
    phases = {
        r["frame"]: r
        for r in json.loads(phase_path.read_text())["rows"]
        if r["region"] == "tail_later"
    }
    rows = []
    for boundary in json.loads(boundary_path.read_text())["rows"]:
        if boundary["allowed_errors"] != 0:
            continue
        frame = boundary["frame"]
        symbol = boundary["boundary"] // 1004 + 1  # Symbol before axis transition.
        phase = phases[frame]
        prediction = phase["polarity"] * WORDS[phase["phase"], (np.arange(1004) - 16 * symbol) % 60]
        values = z[frame, symbol - 2]
        selected = values[-240:]
        backward = []
        for previous in range(symbol - 3, symbol + 1):
            samples = z[frame, previous - 2]
            expected = (
                phase["polarity"] * WORDS[phase["phase"], (np.arange(1004) - 16 * previous) % 60]
            )
            window = samples[-240:]
            backward.append(
                dict(
                    symbol=previous,
                    real_sign=sign_agreement(samples, expected),
                    last240_real_sign=sign_agreement(window, expected[-240:]),
                    last240_imaginary_lag60=sign_agreement(
                        1j * window[60:], np.where(window[:-60].imag <= 0, 1, -1)
                    ),
                )
            )
        pairs, counts = np.unique(
            np.round(np.c_[abs(values.real), abs(values.imag)], 3),
            axis=0,
            return_counts=True,
        )
        target = pairs[counts.argmax()]
        search_start = (symbol - 4) * 1004
        search = z[frame].ravel()[search_start : boundary["boundary"]]
        magnitude_boundaries = []
        for allowed in (0, 2):
            offset = rectangle_boundary(search, target, allowed)
            absolute = None if offset is None else search_start + offset
            magnitude_boundaries.append(
                dict(
                    allowed_errors=allowed,
                    boundary=absolute,
                    residue=None if absolute is None else (absolute + phase["phase"]) % 60,
                )
            )
        rows.append(
            dict(
                frame=frame,
                axis_boundary=boundary["boundary"],
                boundary_carrier=boundary["boundary"] % 1004,
                residue=boundary["residue"],
                previous_symbol=symbol,
                previous_symbol_axis_fraction=float(
                    np.mean((abs(values.imag) < 0.05) & (abs(abs(values.real) - 1) < 0.05))
                ),
                previous_last240=sign_agreement(selected, prediction[-240:]),
                finite_previous_carriers=int(np.isfinite(values).sum()),
                backward_symbols=backward,
                modal_magnitude_pair=target.tolist(),
                magnitude_boundaries=magnitude_boundaries,
            )
        )
    result = dict(
        rows=rows,
        previous_window=240,
        input_sha256={
            str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (source, boundary_path, phase_path, template_path)
        },
        limitation="Fixed tail phase/polarity projected backward, without refitting. "
        "Same recording and template; posthoc region investigation. Sign agreement "
        "is not decoded QAM labels, BER, a header field, or proof of sequence onset. "
        "Marginal baseline is descriptive, not a significance test.",
    )
    (BASE / "local/tail_transition_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    for row in rows:
        print(row["frame"], row["boundary_carrier"], row["residue"], row["previous_last240"])
        if row["residue"] != 0:
            print("magnitude boundaries", row["modal_magnitude_pair"], row["magnitude_boundaries"])


if __name__ == "__main__":
    main()
