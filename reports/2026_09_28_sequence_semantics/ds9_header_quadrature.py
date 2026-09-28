"""Compare shared real/imaginary variation without interpreting it as payload."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent


def correlation(x, y):
    # Remove each symbol/carrier's stationary offset before pooling frames.
    x = x - x.mean(axis=0, keepdims=True)
    y = y - y.mean(axis=0, keepdims=True)
    norm = np.sqrt(np.sum(x * x) * np.sum(y * y))
    return float(np.sum(x * y) / norm) if norm else None


def describe(x, y, threshold):
    combined = (x + y) / 2
    rows = {}
    for axis in ("real", "imag"):
        a, b = getattr(x, axis), getattr(y, axis)
        controls = [correlation(a, np.roll(b, s, axis=0)) for s in range(1, len(a))]
        rows[axis] = dict(
            correlation=correlation(a, b),
            shifted_range=[min(controls), max(controls)],
            shifted_mean=float(np.mean(controls)),
        )
    return dict(
        decisions=int(x.size),
        combined_absolute_real_median=float(np.median(abs(combined.real))),
        retained_fraction=float(np.mean(abs(combined.real) >= threshold)),
        combined_imaginary_energy_fraction=float(
            np.sum(combined.imag**2) / np.sum(abs(combined) ** 2)
        ),
        axes=rows,
    )


def main():
    p = BASE / "local/ds9_combined_reliability.json"
    reliability = json.loads(p.read_text())
    threshold = reliability["per_visit"]["middle"]["thresholds"]["0.5"]
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest()}
    rows = []
    for tag in ("middle", "last"):
        source = BASE / f"local/DS9-{tag}-soft.npz"
        data = np.load(source)
        assert np.array_equal(data["bins0"], data["bins1"])
        frames = reliability["per_visit"][tag]["evaluation_frames"]
        for name, start, stop in [
            ("header_all", 0, 6),
            *[(f"symbol_{s}", s - 2, s - 1) for s in range(2, 8)],
            ("tail", 270, 300),
        ]:
            x, y = [data[f"z{i}"][frames, start:stop] for i in range(2)]
            rows.append(dict(visit=tag, region=name, **describe(x, y, threshold)))
        hashes[str(source)] = hashlib.sha256(source.read_bytes()).hexdigest()
    result = dict(
        rows=rows,
        input_sha256=hashes,
        limitation="Descriptive same-frame receiver covariance, after per-coordinate "
        "centering. Shared channel/calibration/interference can also correlate quadrature. "
        "No modulation identification or payload decoding. Cyclic shifts are controls, "
        "not independent trials or significance estimates.",
    )
    (BASE / "local/ds9_header_quadrature.json").write_text(json.dumps(result, indent=2) + "\n")
    for r in rows:
        print(
            r["visit"],
            r["region"],
            json.dumps({k: v for k, v in r.items() if k not in ("visit", "region")}),
        )


if __name__ == "__main__":
    main()
