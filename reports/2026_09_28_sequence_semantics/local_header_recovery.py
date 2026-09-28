"""Audit changing header signs across independent receivers in cached DS7–DS9."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent


def select_positions(discovery):
    """Use RX0 alone to exclude constant coordinates and set confidence gates."""
    frequency = (discovery.real >= 0).mean(axis=0)
    variable = (frequency >= 0.2) & (frequency <= 0.8)
    confidence = abs(discovery.real) / np.maximum(abs(discovery), 1e-20)
    return variable, np.quantile(confidence, 0.5, axis=0)


def score(left, right, keep):
    if not keep.any():
        return dict(count=0, agreement=None, coordinate_baseline=None)
    a, b = left.real >= 0, right.real >= 0
    count = keep.sum(axis=0)
    p = (a * keep).sum(axis=0) / np.maximum(count, 1)
    q = (b * keep).sum(axis=0) / np.maximum(count, 1)
    baseline = p * q + (1 - p) * (1 - q)
    return dict(
        count=int(keep.sum()),
        agreement=float((a == b)[keep].mean()),
        coordinate_baseline=float((baseline * count).sum() / count.sum()),
    )


def audit(path):
    data = np.load(path)
    bins, left_bins, right_bins = np.intersect1d(data["bins0"], data["bins1"], return_indices=True)
    streams = [data["z0"][:, :, left_bins], data["z1"][:, :, right_bins]]
    metadata = [json.loads(str(data[f"metadata{i}"])) for i in range(2)]
    frames = sorted(set(metadata[0]["evaluation_frames"]) & set(metadata[1]["evaluation_frames"]))
    frames = [
        f
        for f in frames
        if min(m["diagnostics"][f]["held_pilot_coherence"] for m in metadata) > 0.5
    ]
    result = dict(
        signal=path.stem.removesuffix("-soft"),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        qualified_frames=len(frames),
    )
    if len(frames) < 12 or not len(bins):
        return result
    split = len(frames) // 2
    train, evaluation = frames[:split], frames[split:]
    discovery = streams[0][train, :6]
    variable, threshold = select_positions(discovery)
    x, y = [stream[evaluation, :6] for stream in streams]
    confidence = abs(x.real) / np.maximum(abs(x), 1e-20)
    keep = variable[None] & (confidence >= threshold[None])
    # All nonzero cyclic frame shifts retain the same symbol/carrier coordinates.
    # The mask uses RX0 only and stays fixed across the controls.
    controls = [
        score(x, np.roll(y, shift, axis=0), keep)["agreement"]
        for shift in range(1, len(evaluation))
    ]
    per_symbol = [
        dict(
            ofdm_symbol=s + 2,
            variable_positions=int(variable[s].sum()),
            **score(x[:, s], y[:, s], keep[:, s]),
        )
        for s in range(6)
    ]
    raw = []
    for i, frame in enumerate(evaluation):
        symbols = []
        for s in range(6):
            symbols.append(
                dict(
                    ofdm_symbol=s + 2,
                    rx0="".join("1" if b else "0" for b in x[i, s].real >= 0),
                    rx1="".join("1" if b else "0" for b in y[i, s].real >= 0),
                    selected="".join("1" if b else "0" for b in keep[i, s]),
                    consensus="".join(
                        str(int(a)) if selected and a == b else "?"
                        for a, b, selected in zip(
                            x[i, s].real >= 0, y[i, s].real >= 0, keep[i, s], strict=True
                        )
                    ),
                )
            )
        raw.append(dict(frame=int(frame), symbols=symbols))
    valid_controls = [v for v in controls if v is not None]
    result.update(
        discovery_frames=train,
        evaluation_frames=evaluation,
        bins=bins.tolist(),
        variable_positions=int(variable.sum()),
        matched=score(x, y, keep),
        shifted_mean=float(np.mean(valid_controls)) if valid_controls else None,
        shifted_range=[float(min(valid_controls)), float(max(valid_controls))]
        if valid_controls
        else None,
        per_symbol=per_symbol,
        raw_signs=raw,
    )
    return result


def main():
    paths = sorted((BASE / "local").glob("S*-soft.npz")) + sorted(
        (BASE / "local").glob("DS9-*-soft.npz")
    )
    rows = [audit(path) for path in paths]
    output = dict(
        rows=rows,
        scope="Existing cached paired visits from DS7/DS8 and two DS9 visits; "
        "not exhaustive corpus.",
        convention="Template-relative real sign: nonnegative=1. Symbols 2–7, native "
        "FFT bins as listed. ? denotes excluded or disagreeing signs, not an inferred bit.",
        limitation="Receiver agreement is not transmitter BER. Shared distortion remains "
        "possible. Discovery-variable coordinates avoid fixed-template agreement. Frame "
        "shifts are descriptive controls, not independent trials or a significance test. "
        "No field interpretation, FEC, CRC or plaintext validation.",
    )
    (BASE / "local/local_header_recovery.json").write_text(json.dumps(output, indent=2) + "\n")
    for row in rows:
        print(
            json.dumps(
                {
                    k: v
                    for k, v in row.items()
                    if k
                    in (
                        "signal",
                        "qualified_frames",
                        "variable_positions",
                        "matched",
                        "shifted_mean",
                        "shifted_range",
                        "per_symbol",
                    )
                }
            )
        )


if __name__ == "__main__":
    main()
