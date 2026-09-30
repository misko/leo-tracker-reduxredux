"""Audit the frozen counter bank: train-only tie averaging, no new model search."""

import hashlib
import json
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent
OLD = (BASE.parents[3] / "reports") / "2026_09_29_identity_resumption/local/within-visit.json"
PAIRED = (BASE.parents[3] / "reports") / "2026_09_29_ds10_signal_extension/local/paired"


def bank(frames):
    frames = np.asarray(frames)
    return np.array([((frames + phase) % period >= period // 2) ^ invert
                     for period in (2, 4, 8, 16, 32, 64)
                     for phase in range(period) for invert in (False, True)])


def tied_prediction(train_templates, test_templates, discovery):
    correct = (train_templates[:, :, None] == discovery[None]).sum(axis=1)
    tied = correct == correct.max(axis=0)
    probabilities = test_templates.T.astype(float) @ tied / tied.sum(axis=0)
    first = test_templates[correct.argmax(axis=0)].T
    return first, probabilities, tied.sum(axis=0)


def gains(prediction, truth, constant):
    # Expected accuracy of the discovery-tie mixture, not a held-data majority fit.
    return np.where(truth, prediction, 1 - prediction).mean(axis=0) - (
        truth == constant).mean(axis=0)


def tail_rank(maxima):
    """Count numerically equal rational accuracies as ties, conservatively."""
    values = np.asarray(maxima)
    return float(np.mean(values >= values[0] - 1e-12))


def main():
    original = json.loads(OLD.read_text())
    rows = []
    for saved in original["counter"]:
        name = saved["visit"]
        path = PAIRED / name / f"{name}-data-soft.npz"
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        assert sha == original["sources"][name]
        header = json.loads((path.parent / "summary.json").read_text())["header"]
        assert sha == header["sha256"]
        train, test = header["discovery_frames"], header["evaluation_frames"]
        assert set(train).isdisjoint(test) and max(train) < min(test)
        with np.load(path) as data:
            assert np.array_equal(data["bins0"], data["bins1"])
            bins = data["bins0"].tolist()
            discovery = (data["z0"][train, :6].real >= 0).reshape(len(train), -1)
            truth = (data["z1"][test, :6].real >= 0).reshape(len(test), -1)
        frequency = discovery.mean(axis=0)
        selected = np.flatnonzero((frequency >= .2) & (frequency <= .8))
        assert selected.tolist() == saved["coordinates"]
        constant = frequency[selected] >= .5
        truth = truth[:, selected]
        first, mixed, count = tied_prediction(bank(train), bank(test), discovery[:, selected])
        first_scores = gains(first.astype(float), truth, constant)
        np.testing.assert_allclose(first_scores, saved["improvement_over_frozen_constant"],
                                   atol=1e-14, rtol=0)
        assays = []
        for label, prediction in [("original_first", first.astype(float)),
                                   ("training_tie_mixture", mixed)]:
            reference = np.array([gains(prediction, np.roll(truth, s, axis=0), constant)
                                  for s in range(len(test))])
            maximum = reference.max(axis=1)
            rank = tail_rank(maximum)
            strict_rank = float(np.mean(maximum >= maximum[0]))
            if label == "original_first":
                np.testing.assert_allclose(strict_rank, saved["within_visit_maximum_p"])
            assays.append(dict(method=label, maximum_improvement=float(maximum[0]),
                               within_visit_maximum_rank=rank,
                               strict_float_comparison_rank=strict_rank,
                               six_assay_bonferroni_rank=min(1., rank * 6),
                               coordinate_gains=reference[0].tolist(),
                               cyclic_maxima=maximum.tolist()))
        rows.append(dict(visit=name, source=dict(path=str(path), sha256=sha),
                         discovery_frames=train, held_frames=test,
                         coordinates=[[int(k // len(bins) + 2), bins[k % len(bins)]]
                                      for k in selected],
                         tied_model_counts=count.tolist(),
                         coordinates_with_multiple_winners=int((count > 1).sum()),
                         coordinates_with_held_prediction_ambiguity=int(
                             np.any((mixed > 0) & (mixed < 1), axis=0).sum()), assays=assays))
    result = dict(visits=rows,
                  source=dict(path=str(OLD), sha256=hashlib.sha256(OLD.read_bytes()).hexdigest()),
                  method_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  scope="Frozen periods 2/4/8/16/32/64, all phases/polarities; "
                  "RX0 early fits, RX1 late evaluates. Tie mixture weights original bank "
                  "entries equally, not distinct waveforms. No new blind search.",
                  limitation="Reused three same-session excerpts. Circular shifts preserve "
                  "held coordinate dependencies but not physical frame-gap timing. "
                  "Six-assay correction covers two methods times three excerpts; not the "
                  "whole investigation. No mapping to a firmware counter established.")
    (BASE / "local/counter-ties.json").write_text(json.dumps(result, indent=2) + "\n")
    for row in rows:
        print(row["visit"], "ambiguous", row["coordinates_with_held_prediction_ambiguity"],
              "of", len(row["coordinates"]),
              [(a["method"], a["maximum_improvement"], a["within_visit_maximum_rank"])
               for a in row["assays"]])


if __name__ == "__main__":
    main()
