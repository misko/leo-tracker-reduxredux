"""Conditional frequency-permutation controls for two frozen S03 predictors."""
import csv
import hashlib
import json
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
REPLICATES = 32
SEED = 39501020


def permuted_indices(receiver, channel, mask, rng):
    receiver, channel, mask = np.asarray(receiver), np.asarray(channel), np.asarray(mask)
    if receiver.shape!=channel.shape or receiver.shape!=mask.shape or mask.dtype!=bool:
        raise ValueError('Aligned receiver/channel metadata and boolean mask required')
    indices = np.arange(len(mask))
    for rx, ch in sorted(set(zip(receiver[mask].tolist(), channel[mask].tolist()))):
        rows = np.flatnonzero(mask & (receiver==rx) & (channel==ch))
        indices[rows] = rng.permutation(rows)
    return indices


def main():
    from leo.analysis.shared_scan_model import density
    from leo.contracts.regional_position import POSITION_SCORES
    bindings = {}

    def bind(path):
        bindings[str(path.relative_to(REPORTS))] = 'sha256:'+hashlib.sha256(path.read_bytes()).hexdigest()
        return path

    path = REPORTS/'2026_10_16_dsx01_fast_association_losses/context-observations.jsonl'
    metadata = [json.loads(line) for line in bind(path).read_text().splitlines()]
    metadata = [r for r in metadata if r['source_id']=='S03']
    measured = np.array([r['measured_cfo_hz'] for r in metadata])
    receiver = np.array([r['receiver'] for r in metadata])
    channel = np.array([r['channel'] for r in metadata])
    membership = REPORTS/'2026_10_16_dsx01_fast_association_losses/membership.csv'
    with bind(membership).open() as stream:
        challenge_ids = {r['observation_id'] for r in csv.DictReader(stream) if r['source_id']=='S03'}
    challenge = np.array([r['observation_id'] in challenge_ids for r in metadata])
    models = {
        'half-forecast': (REPORTS/'2026_10_17_dsx01_iteration4/cold_pipeline/S03-early_to_late', 'held-predictions.npz'),
        'blocked-interpolation': (REPORTS/'2026_10_17_dsx01_iteration5/blocked_cold/S03-block20-parity0', 'predictions.npz')}
    result = []
    replicates = []
    for name, (attempt, filename) in models.items():
        with np.load(bind(attempt/filename)) as arrays:
            prediction = dict(arrays)
        with np.load(bind(attempt/'evaluation.npz')) as arrays:
            saved = dict(arrays)
        evaluation = json.loads(bind(attempt/'evaluation.json').read_text())
        np.testing.assert_allclose(prediction['times_s'], [r['time_s'] for r in metadata], atol=1e-9, rtol=0)
        score = POSITION_SCORES['V16']
        def classify(y):
            terms, details = density(y, prediction['prediction_hz'], prediction['visibility_weight'],
                np.full(len(y), 125.), prediction['detection_probability'], score)
            best = terms.responsibilities.argmax(axis=1)
            assigned = terms.responsibilities[np.arange(len(best)), best] > terms.clutter_probability
            return assigned, details['row_nll']
        actual, nll = classify(measured)
        np.testing.assert_array_equal(actual, saved['associated'])
        held = prediction['held_mask']
        assert int(actual[held].sum())==evaluation['held']['associated']
        rng = np.random.default_rng(SEED)
        for replicate in range(REPLICATES):
            order = permuted_indices(receiver, channel, held, rng)
            null, null_nll = classify(measured[order])
            # Training inputs and scoring never change under this held-only control.
            np.testing.assert_array_equal(null[~held], actual[~held])
            replicates.append(dict(model=name, replicate=replicate,
                full_held_assigned=int(null[held].sum()), challenge_held_assigned=int(null[held & challenge].sum()),
                held_nll=float(null_nll[held].sum())))
        rows = [r for r in replicates if r['model']==name]
        for label, use, key in [('full-held', held, 'full_held_assigned'),
                                ('challenge-held', held & challenge, 'challenge_held_assigned')]:
            values = np.array([r[key] for r in rows])
            result.append(dict(model=name, scope=label, denominator=int(use.sum()),
                actual_assigned=int(actual[use].sum()), actual_assigned_pct=100*float(actual[use].mean()),
                null_mean_assigned=float(values.mean()), null_min_assigned=int(values.min()),
                null_max_assigned=int(values.max()), null_std_assigned=float(values.std()),
                replicates=REPLICATES,actual_held_nll=float(nll[use].sum())))
    for filename, rows in [('summary.csv', result), ('replicates.csv', replicates)]:
        with (HERE/filename).open('w') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    receipt = dict(seed=SEED, replicates=REPLICATES, summary=result, inputs=bindings,
        code_sha256='sha256:'+hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        qualification='Read-only conditional controls on fitted-c production predictors; no fitting or c-effect comparison. Held CFO is permuted within receiver/channel, retaining its marginal frequency distribution and fixed prediction/q/calibration. This tests temporal alignment, not identity correctness or a calibrated discovery false-positive rate. Cohorts differ between the two predictors; no causal attribution across them.')
    (HERE/'receipt.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__=='__main__':
    main()
