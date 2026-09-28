"""Apply frozen reference checks to combined header estimates, without correction."""

import hashlib
import json
from pathlib import Path

import numpy as np
from local_reference_parity import measure

BASE = Path(__file__).parent


def main():
    reference_path = BASE / "local/lower_edge_parity.json"
    reference = json.loads(reference_path.read_text())
    equations = [
        r for r in reference["rows"] if r["evaluation_count"] == 39 and r["evaluation_errors"] == 0
    ]
    hashes = {str(reference_path): hashlib.sha256(reference_path.read_bytes()).hexdigest()}
    reliability_path = BASE / "local/ds9_combined_reliability.json"
    reliability = json.loads(reliability_path.read_text())
    thresholds = reliability["per_visit"]["middle"]["thresholds"]
    hashes[str(reliability_path)] = hashlib.sha256(reliability_path.read_bytes()).hexdigest()
    rows = []
    for tag in ("middle", "last"):
        source = BASE / f"local/DS9-{tag}-combined-header.npz"
        original_path = BASE / f"local/DS9-{tag}-soft.npz"
        data = np.load(source)
        assert str(data["source_sha256"]) == hashlib.sha256(original_path.read_bytes()).hexdigest()
        bins = {int(b): i for i, b in enumerate(data["bins"])}
        frames = data["evaluation_frames"]
        for equation in equations:
            values = np.stack(
                [data["soft"][frames, s - 2, bins[b]] for s, b in equation["coordinates"]], axis=1
            )
            bits = (values.real >= 0).astype(np.uint8)
            gate = (abs(values.real) / np.maximum(abs(values), 1e-20) > 0.9).all(axis=1)
            observed = measure(bits, equation["parity"])
            amplitude_gates = []
            for q in ("0.5", "0.75", "0.9"):
                threshold = thresholds[q]
                qualified = (abs(values.real) >= threshold).all(axis=1)
                amplitude_gates.append(
                    dict(
                        training_visit="middle",
                        quantile=float(q),
                        threshold=threshold,
                        **measure(bits[qualified], equation["parity"]),
                    )
                )
            controls = []
            for shift in range(1, len(bits)):
                shifted = bits.copy()
                shifted[:, 0] = np.roll(shifted[:, 0], shift)
                controls.append(measure(shifted, equation["parity"])["agreement"])
            rows.append(
                dict(
                    tag=tag,
                    coordinates=equation["coordinates"],
                    parity=equation["parity"],
                    frames=frames.tolist(),
                    all=observed,
                    tail_trained_amplitude_gates=amplitude_gates,
                    axis_gated=measure(bits[gate], equation["parity"]),
                    shifted_first_constituent_mean=float(np.mean(controls)),
                    shifted_first_constituent_range=[float(min(controls)), float(max(controls))],
                    raw_bit_strings=["".join(map(str, b)) for b in bits],
                    confidence_gate=gate.tolist(),
                )
            )
        for p in (source, original_path):
            hashes[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    output = dict(
        rows=rows,
        input_sha256=hashes,
        limitation="Frozen reference parity and equal receiver weighting; later23 "
        "DS9 frames used. No comparison to component receivers as truth. Tail "
        "combining improvement does not guarantee header accuracy. Marginal and "
        "shifted baselines descriptive; confidence gate does not select parity success.",
    )
    (BASE / "local/combined_header_parity.json").write_text(json.dumps(output, indent=2) + "\n")
    print(
        json.dumps(
            [
                {
                    k: v
                    for k, v in r.items()
                    if k not in ("frames", "raw_bit_strings", "confidence_gate")
                }
                for r in rows
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
