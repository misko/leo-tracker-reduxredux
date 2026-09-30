"""Frozen public parity on combined DS10 signs, with fixed-mask shift controls."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent


def evaluate(values, parity, threshold):
    bits = (values >= 0).astype(np.uint8)
    keep = (abs(values) >= threshold).all(axis=1)
    count = int(keep.sum())
    if not count:
        return dict(count=0, agreement=None, baseline=None, shifted_mean=None)
    selected = bits[keep]
    agreement = float((np.bitwise_xor.reduce(selected, axis=1) == parity).mean())
    baseline = float((1 + (-1) ** parity * np.prod(1 - 2 * selected.mean(axis=0))) / 2)
    controls = []
    for shift in range(1, len(bits)):
        shifted = bits.copy()
        shifted[:, 0] = np.roll(bits[:, 0], shift)
        controls.append(float((np.bitwise_xor.reduce(shifted[keep], axis=1) == parity).mean()))
    return dict(count=count, agreement=agreement, baseline=baseline,
                shifted_mean=float(np.mean(controls)), shifted_max=float(np.max(controls)))


def main():
    reference = BASE.parent / "2026_09_28_sequence_semantics/local/lower_edge_parity.json"
    equations = [r for r in json.loads(reference.read_text())["rows"]
                 if r["evaluation_count"] == 39 and r["evaluation_errors"] == 0]
    combining = BASE / "local/within-visit/receiver-combining/summary.json"
    rows, hashes = [], {}
    for visit in json.loads(combining.read_text())["visits"]:
        name = visit["visit"]
        path = BASE / f"local/within-visit/receiver-combining/{name}.npz"
        raw_path = BASE / f"local/paired/{name}/{name}-data-soft.npz"
        digest = hashlib.sha256(raw_path.read_bytes()).hexdigest()
        assert digest == visit["source_sha256"]
        with np.load(path) as data, np.load(raw_path) as raw:
            lookup = {int(b): i for i, b in enumerate(data["bins"])}
            expected = (raw["z0"][data["frames"], :6].real
                        + raw["z1"][data["frames"], :6].real) / 2
            assert np.array_equal(data["equal_soft"], expected)
            for equation in equations:
                for mode, field, gates in [("equal", "equal_soft", "equal_gates"),
                                            ("weighted", "soft", "gates")]:
                    values = np.column_stack([data[field][:, s - 2, lookup[b]]
                                              for s, b in equation["coordinates"]])
                    results = [dict(quantile=g["quantile"], threshold=g["threshold"],
                                    **evaluate(values, equation["parity"], g["threshold"]))
                               for g in visit[gates]]
                    rows.append(dict(visit=name, mode=mode, coordinates=equation["coordinates"],
                                     parity=equation["parity"], frames=data["frames"].tolist(),
                                     signs=(values >= 0).astype(int).tolist(), gates=results))
        for p in (path, raw_path):
            hashes[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    for p in (reference, combining, Path(__file__)):
        hashes[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    result = dict(rows=rows, input_sha256=hashes,
                  limitation="Equation unchanged from public reference. Thresholds from earlier "
                  "tail samples, no parity-success selection. All constituents must pass. "
                  "First-constituent cyclic shifts preserve target-frame mask but not the donor's "
                  "amplitude eligibility; descriptive controls only. No FEC correction.")
    (BASE / "local/within-visit/combined-parity.json").write_text(
        json.dumps(result, indent=2) + "\n")
    for r in rows:
        print(r["visit"], r["mode"], r["gates"])


if __name__ == "__main__":
    main()
