"""Lower-edge reliability-profile transfer with frequency-rotation controls."""

import hashlib
import itertools
import json
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
OLD = BASE.parents[1] / "starlink_firmware/apk_fw_v1/reports/2026_09_28_sequence_semantics"
PAIRED = BASE.parent / "2026_09_29_ds10_signal_extension/local/paired"
sys.path.insert(0, str(OLD))
from pilot_distance_structure import soft_correlations  # noqa: E402


def centered_score(x, y, mask, bins):
    """Remove symbol and pilot-flank means before comparing coordinate profiles."""
    left, right = [], []
    for s in range(len(x)):
        for flank in (bins < 528, bins > 535):
            good = mask[s] & flank & np.isfinite(x[s]) & np.isfinite(y[s])
            if good.sum() >= 3:
                a, b = x[s, good], y[s, good]
                left.extend(a - a.mean())
                right.extend(b - b.mean())
    if len(left) < 12 or np.std(left) < 1e-10 or np.std(right) < 1e-10:
        return None
    return float(np.corrcoef(left, right)[0, 1])


def rotate(profile, bins, shifts):
    result = profile.copy()
    for flank, shift in zip((bins < 528, bins > 535), shifts, strict=True):
        result[:, flank] = np.roll(profile[:, flank], shift, axis=1)
    return result


def main():
    receipts = {}
    inputs = []
    old_path = OLD / "local/local_header_recovery.json"
    receipts[str(old_path)] = hashlib.sha256(old_path.read_bytes()).hexdigest()
    r = next(v for v in json.loads(old_path.read_text())["rows"]
             if v["signal"] == "DS9-middle")
    inputs.append(("DS9-middle", OLD / "local/DS9-middle-soft.npz", r))
    for name in ("DS10-F010-v1085", "DS10-F010-v1150", "DS10-F010-v1162"):
        path = PAIRED / name / "summary.json"
        receipts[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        inputs.append((name, PAIRED / name / f"{name}-data-soft.npz",
                       json.loads(path.read_text())["header"]))
    bins = None
    for _, path, r in inputs:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == r["sha256"]
        receipts[str(path)] = r["sha256"]
        with np.load(path) as d:
            common = np.intersect1d(d["bins0"], d["bins1"])
            common = common[(common < 528) | (common > 535)]
            bins = common if bins is None else np.intersect1d(bins, common)
    profiles = {}
    for name, path, r in inputs:
        with np.load(path) as d:
            a = d["z0"][:, :6, np.searchsorted(d["bins0"], bins)]
            b = d["z1"][:, :6, np.searchsorted(d["bins1"], bins)]
        tr, ev = r["discovery_frames"], r["evaluation_frames"]
        frequency = (a[tr].real >= 0).mean(axis=0)
        profiles[name] = dict(mask=(frequency >= .2) & (frequency <= .8),
                              train=soft_correlations(a[tr], b[tr]),
                              test=soft_correlations(a[ev], b[ev]),
                              frames=[len(tr), len(ev)])
    rotations = list(itertools.product(range(int((bins < 528).sum())),
                                       range(int((bins > 535).sum()))))
    rows = []
    for donor, p in profiles.items():
        for target, q in profiles.items():
            for metric, label in ((0, "complex_phase"), (1, "real_phase")):
                x, y = p["train"][metric], q["test"][metric]
                observed = centered_score(x, y, p["mask"], bins)
                controls = [centered_score(x, rotate(y, bins, shift), p["mask"], bins)
                            for shift in rotations if shift != (0, 0)]
                valid = [v for v in controls if v is not None]
                pvalue = None if observed is None else (
                    1 + sum(v >= observed for v in valid)) / (1 + len(valid))
                rows.append(dict(donor=donor, target=target, metric=label,
                                 correlation=observed, controls=len(valid),
                                 circular_p=pvalue,
                                 family_p=None if pvalue is None else min(1., 32 * pvalue),
                                 control_95=float(np.quantile(valid, .95))))
    result = dict(bins=bins.tolist(), visits={k: v["frames"] for k, v in profiles.items()},
                  comparisons=rows, source_sha256=receipts,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Reliability profiles, not message-bit or identity agreement. "
                  "DS10 candidates are conditional, DS9 identity not asserted. Reused data, "
                  "chronological fit holdout. Whole-flank circular shifts preserve frequency "
                  "adjacency except the wrap; exchangeability is approximate. Bonferroni 32 "
                  "comparisons. Small frame counts make individual profiles noisy.")
    (BASE / "local/lower-profile-transfer.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
