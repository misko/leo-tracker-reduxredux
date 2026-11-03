"""Verify sealed results and independently replay per-row orbit interpolation."""
import json
from pathlib import Path

import numpy as np

import run


def main():
    p = run
    plan = p.read(run.HERE/'plan.json')
    outcome = p.read(run.HERE/'outcome.json')
    selection = p.read(run.HERE/'selections.json')
    assert outcome['plan_sha256'] == p.digest(run.HERE/'plan.json')
    for path, expected in outcome['sources'].items():
        assert p.digest(path) == expected, path
    docs, fast, _, harness = p.context(plan)
    accepted_counts = {arm:sum(r['pilot_used'] for r in rows) for arm,rows in plan['corrections'].items()}
    for arm, corrections in plan['corrections'].items():
        for row in corrections:
            if not row['pilot_used']:
                assert row['delta_hz'] == row['nominal_support_shift_s'] == 0.
            else:
                assert row['delta_hz'] == row['proposed_pilot_delta_hz'] and row['nominal_support_shift_s'] < 0.
    diagnosis_path = p.HILL/'source_loo/diagnose.py'
    diagnosis = p.module('support_result_diagnosis', diagnosis_path)
    _, _, _, verified, sidecar, mappings = diagnosis.validate_inputs(16)
    assert [t['track_id'] for t in docs[0]['tracks']] == [t['track_id'] for t in verified[0]['tracks']]
    summaries = {}
    assignments = {}
    for arm in ('control',) + p.ARMS:
        changed = docs if arm == 'control' else run.patch_documents(docs, plan['corrections'][arm])
        row = outcome['control'] if arm == 'control' else outcome['selected'][arm]
        x = np.asarray(row['x'])
        geometry = run.SUPPORT.SupportStationary(changed[0], plan['config'])
        original = run.SUPPORT.OriginalStationary(changed[0], plan['config'])
        max_discrepancy = 0.
        assignments[arm] = {}
        for track in changed[0]['tracks']:
            predictions, visible = geometry.prediction(track, x)
            shifts = track.get('nominal_support_shift_s', np.zeros(len(track['y'])))
            for index in np.flatnonzero(shifts):
                scalar_x = x.copy(); scalar_x[2] += shifts[index]
                scalar = original.prediction(track, scalar_x)[0][:, index]
                max_discrepancy = max(max_discrepancy, float(np.max(abs(predictions[:, index]-scalar))))
            np.testing.assert_array_equal(predictions[:, ~track['mask']],
                                          original.prediction(track, x)[0][:, ~track['mask']])
            train, _, audits, _ = fast.profile(track['y'][None, :]-predictions, track['mask'])
            assert all(r['converged'] for r in audits)
            j = int(np.argmax(np.where(visible, train, -np.inf)))
            assignments[arm][track['track_id']] = mappings[0][track['track_id']][j]
        assert max_discrepancy < 1e-8
        assert abs(harness.distance(row['estimate_deg'])-row['error_m']) < 1e-8
        summaries[arm] = dict(max_scalar_prediction_discrepancy_hz=max_discrepancy)
        if arm != 'control':
            attempts = [r for r in outcome['attempts'] if r['job']['arm'] == arm]
            assert len(attempts) == 4
            assert all(r['receipt']['exit_code'] == 0 and r['result']['endpoint']['qualified'] for r in attempts)
            endpoints = [r['result']['endpoint'] for r in attempts]
            chosen = max(endpoints, key=lambda r:r['score'])
            # assess adds geography to the selected in-memory endpoint after
            # writing the reference-free selection; all other fields match.
            assert {k:v for k,v in chosen.items() if k != 'error_m'} == selection['selected'][arm]
            assert chosen['x'] == row['x']
            spread = max(float(np.linalg.norm(np.asarray(a['x'][:2])-b['x'][:2])*1000)
                         for a in endpoints for b in endpoints)
            summaries[arm].update(qualified_starts=4, maximum_start_spread_en_m=spread,
                                 error_change_m=row['error_m']-outcome['control']['error_m'])
    changed = {arm: sum(v != assignments['control'][k] for k,v in assignments[arm].items()) for arm in p.ARMS}
    paths = [Path(__file__), run.HERE/'outcome.json', run.HERE/'plan.json', sidecar, diagnosis_path]
    result = dict(schema='ds11-pilot-fallback-position-verification/v1', summaries=summaries,
                  conditional_assignments=assignments, changed_map_norads=changed,
                  identities_authenticated=False, position_refits=0, accepted_counts=accepted_counts,
                  sources={str(path):p.digest(path) for path in paths})
    p.write(run.HERE/'verification.json', result)
    print(json.dumps(dict(summaries=summaries, changed_map_norads=changed), indent=2))


if __name__ == '__main__':
    main()
