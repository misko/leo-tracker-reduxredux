"""Chronological RX0-to-RX1 prediction beyond the known T-code waveform."""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE.parent / "2026_09_29_all_track_symbols"))
from decode_tracks import SEED, codebook, slots  # noqa: E402
from state_residuals import expand, fit_gain  # noqa: E402


def templates(x, labels, target_labels):
    return np.array([x[labels == state].mean(axis=0) for state in target_labels])


def improvement(target, prediction, baseline):
    base_error = np.mean(abs(target - baseline) ** 2)
    return float(1 - np.mean(abs(target - prediction) ** 2) / max(base_error, 1e-20))


def transfer(train, target, train_states, target_states, permutations):
    """Fixed eligible states; permutation retains state counts and target samples."""
    baseline = train.mean(axis=0)
    predicted = templates(train, train_states, target_states)
    value = improvement(target, predicted, baseline)
    controls = [improvement(target, templates(train, p, target_states), baseline)
                for p in permutations]
    return dict(
        state_over_global_error_reduction=value,
        state_over_zero_error_reduction=improvement(target, predicted, 0),
        global_over_zero_error_reduction=improvement(target, baseline, 0),
        shuffled_state_mean=float(np.mean(controls)),
        shuffled_state_max=float(np.max(controls)),
        shuffled_state_exceedances=sum(c >= value for c in controls),
        controls=len(controls),
    )


def analyze(path):
    source = json.loads((path.parent / "summary.json").read_text())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == source["header"]["sha256"]
    state = {w["frame"]: w["phase_hypothesis"] for w in source["windows"]
             if w["label"] == 1}
    qualified = source["qualified_frames"]
    split = len(qualified) // 2
    train_frames = [f for f in qualified[:split] if f in state]
    test_frames = [f for f in qualified[split:] if f in state]
    labels = np.array([state[f] for f in train_frames])
    eligible = [int(s) for s in np.unique(labels) if (labels == s).sum() >= 2]
    test_frames = [f for f in test_frames if state[f] in eligible]
    result = dict(visit=path.parent.name, source_sha256=digest,
                  train_frames=train_frames, test_frames=test_frames,
                  eligible_states=eligible, qualified_frames=len(qualified))
    if len(train_frames) < 4 or len(test_frames) < 4 or len(eligible) < 2:
        return dict(**result,
                    abstention="Need >=4 train/test frames and >=2 repeated training states")
    with np.load(path) as d:
        assert np.array_equal(d["bins0"], d["bins1"])
        bins = d["bins0"]
        a, b = d["z0"][train_frames], d["z1"][test_frames]
    target_labels = np.array([state[f] for f in test_frames])
    words = np.array([[1 if v == "1" else -1 for v in word]
                      for word in codebook(list(map(int, SEED)))])
    mapping = slots(bins, np.arange(2, 302))
    p, q = words[labels][:, mapping], words[target_labels][:, mapping]
    rng = np.random.default_rng(20260929)
    permutations = [rng.permutation(labels) for _ in range(199)]
    result.update(train_states=labels.tolist(), test_states=target_labels.tolist(), assays=[])
    for carrier in (False, True):
        ga, gb = fit_gain(a, p, per_carrier=carrier), fit_gain(b, q, per_carrier=carrier)
        # Multiplicative gain normalization could magnify weak carriers; instead
        # subtract the independently fitted waveform in the original soft units.
        ra, rb = a - expand(ga) * p, b - expand(gb) * q
        for start, stop in [(0, 6), (6, 32), (32, 128), (128, 192), (256, 288)]:
            result["assays"].append(dict(
                gain_model="per_carrier" if carrier else "scalar",
                symbols=[start + 2, stop + 1],
                residual=transfer(ra[:, start:stop], rb[:, start:stop],
                                  labels, target_labels, permutations),
                raw=transfer(a[:, start:stop], b[:, start:stop],
                             labels, target_labels, permutations),
            ))
    return result


def main():
    rows = [analyze(p) for p in sorted((BASE / "local/paired").glob("*/*-data-soft.npz"))]
    out = BASE / "local/within-visit/state-transfer.json"
    out.parent.mkdir(exist_ok=True)
    result = dict(visits=rows,
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation="Chronological cross-receiver prediction; descriptive 199 shuffled "
                  "training-label controls, no independent-trial p-values. State selection from "
                  "194–225 and gain fit 226–257 are disjoint from test regions. Residual patterns "
                  "may reflect state-dependent model error or common calibration, "
                  "not message bits.")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
