"""Held-frame I/Q reproducibility after discovery-only offsets and leakage fits."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent


def remove_offset_and_leakage(train, test):
    center = train.mean(axis=0)
    a, b = train - center, test - center
    slope = (a.real * a.imag).sum(axis=0) / np.maximum((a.real ** 2).sum(axis=0), 1e-20)
    return b.real, b.imag, b.imag - slope * b.real, center, slope


def compare(a, b):
    def corr(x, y):
        # Center each coordinate across evaluation frames for covariance only.
        # This does not fit any sign thresholds or leakage coefficients.
        x, y = x - x.mean(axis=0), y - y.mean(axis=0)
        return float(np.sum(x * y) / max(np.linalg.norm(x) * np.linalg.norm(y), 1e-20))

    bits0, bits1 = a >= 0, b >= 0
    p, q = bits0.mean(axis=0), bits1.mean(axis=0)
    controls = [float((bits0 == np.roll(bits1, k, axis=0)).mean())
                for k in range(1, len(a))]
    covariance_controls = [corr(a, np.roll(b, k, axis=0)) for k in range(1, len(a))]
    return dict(sign_decisions=a.size, agreement=float((bits0 == bits1).mean()),
                bias_baseline=float((p * q + (1 - p) * (1 - q)).mean()),
                shifted_agreement_mean=float(np.mean(controls)),
                shifted_agreement_max=float(np.max(controls)),
                centered_correlation=corr(a, b),
                shifted_correlation_max=float(np.max(covariance_controls)))


def main():
    out = BASE / "local/within-visit/early-iq"
    out.mkdir(exist_ok=True)
    visits = []
    for path in sorted((BASE / "local/paired").glob("*/*-data-soft.npz")):
        summary_path = path.parent / "summary.json"
        summary = json.loads(summary_path.read_text())
        h = summary["header"]
        if "evaluation_frames" not in h:
            continue
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        assert digest == h["sha256"]
        train, test = h["discovery_frames"], h["evaluation_frames"]
        with np.load(path) as d:
            assert np.array_equal(d["bins0"], d["bins1"])
            bins = d["bins0"]
            values = [remove_offset_and_leakage(d[f"z{rx}"][train, :6],
                                               d[f"z{rx}"][test, :6]) for rx in range(2)]
        rows = []
        for k, name in enumerate(["I_centered", "Q_centered", "Q_after_local_I_regression"]):
            x, y = values[0][k], values[1][k]
            rows.append(dict(component=name, symbols=[2, 7], **compare(x, y)))
            for s in range(6):
                rows.append(dict(component=name, symbols=[s + 2, s + 2],
                                 **compare(x[:, s], y[:, s])))
        # A per-frame, per-symbol mean removes a common additive carrier level.
        # It cannot remove general multiplicative gain or frequency-selective error.
        x, y = [v[0] - v[0].mean(axis=2, keepdims=True) for v in values]
        rows.append(dict(component="I_without_common_carrier_level", symbols=[2, 7],
                         **compare(x, y)))
        for s in range(6):
            rows.append(dict(component="I_without_common_carrier_level",
                             symbols=[s + 2, s + 2], **compare(x[:, s], y[:, s])))
        detrended = []
        for v in values:
            template = v[3].real - v[3].real.mean(axis=1, keepdims=True)
            residual = v[0] - v[0].mean(axis=2, keepdims=True)
            gain = (residual * template).sum(axis=2, keepdims=True) / np.maximum(
                (template ** 2).sum(axis=1, keepdims=True), 1e-20)
            detrended.append(residual - gain * template)
        for s in range(6):
            rows.append(dict(component="I_without_common_level_or_template_gain",
                             symbols=[s + 2, s + 2],
                             **compare(detrended[0][:, s], detrended[1][:, s])))
        cache = out / f"{path.parent.name}.npz"
        np.savez_compressed(cache, frames=test, bins=bins,
                            rx0=np.stack(values[0][:3]), rx1=np.stack(values[1][:3]),
                            detrended_i0=detrended[0], detrended_i1=detrended[1],
                            center0=values[0][3], center1=values[1][3],
                            slope0=values[0][4], slope1=values[1][4])
        visits.append(dict(visit=path.parent.name, source_sha256=digest,
                           summary_sha256=hashlib.sha256(summary_path.read_bytes()).hexdigest(),
                           output_sha256=hashlib.sha256(cache.read_bytes()).hexdigest(),
                           train_frames=train, evaluation_frames=test, rows=rows))
    result = dict(visits=visits,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitations="Discovery-only per-coordinate complex mean and real I-to-Q slope, "
                  "separately per RX. No axis optimization, no confidence gating. Shared channel "
                  "errors or adjacent-carrier leakage may survive. Signs are not validated QAM "
                  "bits. Cyclic controls are descriptive; coordinates and frames are dependent.")
    (out / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    for r in visits:
        print(r["visit"])
        for row in r["rows"]:
            if row["symbols"] == [2, 7]:
                print(row)


if __name__ == "__main__":
    main()
