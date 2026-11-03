"""Post-seal comparison to the original TRAIN-only cold prediction, no fitting."""
import csv
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from leo.analysis.shared_scan_model import density

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parents[1]
PILOT = HERE.parent/'coherent_pilot'
OLD = REPORTS/'2026_10_17_dsx01_iteration5/blocked_cold'
ATTEMPT = OLD/'S03-block20-parity0'
DATA = REPORTS/'2026_10_16_dsx01_fast_association_losses'


def sha(path):
    return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def rms(values):
    return float(np.sqrt(np.mean(np.square(values)))) if len(values) else None


def paired(mask, old, new):
    mask = np.asarray(mask)
    if mask.dtype != bool or mask.ndim != 1:
        raise ValueError('One-dimensional boolean role mask required')
    for state in (old, new):
        if any(np.asarray(state[k]).shape != mask.shape
               for k in ('associated', 'residual_hz', 'number', 'row_nll')):
            raise ValueError('Aligned observation states required')
    a, b = old['associated'], new['associated']
    both = mask & a & b
    return dict(observations=int(mask.sum()), original=int((mask & a).sum()),
        associated=int((mask & b).sum()), new=int((mask & b & ~a).sum()),
        lost=int((mask & a & ~b).sum()), retained=int(both.sum()),
        retained_identity_changes=int((both & (old['number'] != new['number'])).sum()),
        original_nll=float(old['row_nll'][mask].sum()),
        current_nll=float(new['row_nll'][mask].sum()),
        intersection_original_rms_hz=rms(old['residual_hz'][both]),
        intersection_current_rms_hz=rms(new['residual_hz'][both]))


def main():
    inputs = {}

    def bind(path):
        inputs[str(path)] = sha(path)
        return path

    for name, key in (('outcomes_seal.json', 'outcomes'), ('predictions_seal.json', 'predictions')):
        seal = read(bind(PILOT/'inference_results'/name))
        assert seal['all_four_sealed'] and len(seal[key]) == 4
        for item in seal[key]:
            assert sha(item['path']) == item['sha256']
    original_manifest = read(bind(OLD/'manifest.json'))['files']
    authorities = {row['path']: row['sha256'] for row in original_manifest}
    for name in ('evaluation.npz', 'predictions.npz', 'evaluation.json', 'derivation.json',
                 'context-verification.json'):
        path = ATTEMPT/name
        assert sha(path) == authorities[str(path.relative_to(OLD))]
        bind(path)
    old_evaluation = read(ATTEMPT/'evaluation.json')
    assert sha(ATTEMPT/'predictions.npz') == old_evaluation['prediction_sha256']
    with np.load(ATTEMPT/'predictions.npz', allow_pickle=False) as a:
        prediction = dict(a)
    with np.load(ATTEMPT/'evaluation.npz', allow_pickle=False) as a:
        saved = dict(a)
    rows = [json.loads(line)
            for line in bind(DATA/'context-observations.jsonl').read_text().splitlines()]
    rows = [row for row in rows if row['source_id'] == 'S03']
    ids = np.array([r['observation_id'] for r in rows])
    times = np.array([r['time_s'] for r in rows])
    y = np.array([r['measured_cfo_hz'] for r in rows])
    np.testing.assert_array_equal(times, saved['times_s'])
    np.testing.assert_array_equal(times, prediction['times_s'])
    source_score = read(PILOT/'inference_results/outcomes_seal.json')['original_shared_score']
    terms, details = density(y, prediction['prediction_hz'], prediction['visibility_weight'],
        np.full(len(y), 125.), prediction['detection_probability'], SimpleNamespace(**source_score))
    best = terms.responsibilities.argmax(axis=1)
    at = np.arange(len(y))
    old = dict(associated=terms.responsibilities[at, best] > terms.clutter_probability,
        residual_hz=terms.residual_hz[at, best], number=prediction['number'][best],
        row_nll=details['row_nll'])
    np.testing.assert_array_equal(old['associated'], saved['associated'])
    np.testing.assert_array_equal(old['number'], saved['satellite_number'])
    np.testing.assert_allclose(old['residual_hz'], saved['residual_hz'], atol=1e-9, rtol=0)
    np.testing.assert_allclose(old['row_nll'].sum(), old_evaluation['full']['frequency_nll'],
                               atol=1e-7, rtol=0)
    with bind(DATA/'membership.csv').open() as stream:
        members = [r for r in csv.DictReader(stream) if r['source_id'] == 'S03']
    masks = {role: saved[role+'_mask'] for role in ('train', 'held', 'boundary')}
    masks['full'] = np.ones(len(y), bool)
    masks['requested_held'] = np.isin(ids, [r['observation_id'] for r in members]) & masks['held']
    counts = [int(masks[r].sum()) for r in ('train', 'held', 'boundary', 'requested_held')]
    assert counts == [2073, 1909, 6, 80]
    assert (masks['held'] & old['associated']).sum() == 795
    assert (masks['requested_held'] & old['associated']).sum() == 66
    result = {}
    for case in ('independent_fitted-c', 'automatic_fitted-c',
                 'independent_zero-c', 'automatic_zero-c'):
        with np.load(bind(PILOT/f'evaluation_{case}.npz'), allow_pickle=False) as a:
            state = dict(a)
        np.testing.assert_array_equal(state['observation_id'], ids)
        np.testing.assert_array_equal(state['times_s'], times)
        for role in ('train', 'held', 'boundary'):
            np.testing.assert_array_equal(state[role+'_mask'], masks[role])
        new = {k: state['original_shared_'+key] for k, key in
               [('associated', 'associated'), ('residual_hz', 'residual_hz'),
                ('number', 'best_number'), ('row_nll', 'row_nll')]}
        metrics = {role: paired(mask, old, new) for role, mask in masks.items()}
        metrics['windows'] = {rid: paired(masks['held'] & np.isin(ids,
            [r['observation_id'] for r in members if r['region_id'] == rid]), old, new)
            for rid in sorted({r['region_id'] for r in members})}
        result[case] = metrics
    payload = dict(passed=True, rows=result, source_bindings=inputs, original_density_calls=1,
        original_baseline='Same fitted-c TRAIN-only cold endpoint for all four arms',
        paired_classifier='Original shared-q density only; no native-group count substitution',
        alignment=('Older NPZ lacks IDs; frozen source ordering/timestamps/masks plus exact '
            'posterior, identity and residual replay checked against current observation IDs'),
        qualification=('Descriptive original-vs-new comparison. Changed likelihood, free bands, '
            'broad domain and extra optimization prevent causal attribution. Matched '
            'independent/coherent comparison is separate.'),
        no_new_fits=True, no_reference_reads=True, old_prediction_replayed_exactly=True)
    with (HERE/'summary.json').open('x') as stream:
        json.dump(payload, stream, indent=2, allow_nan=False)
        stream.write('\n')
    print(json.dumps({k:dict(held=v['held'], requested_held=v['requested_held'])
                      for k, v in result.items()}, indent=2))


if __name__ == '__main__':
    main()
