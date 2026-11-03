"""Audit failure examples and nested-model search gaps from the frozen snapshot.

No fitting: reconstruct the timing penalty using the deployed orthonormal
zero-sum timing basis, then subtract it from each saved objective. Comparisons
across basins include their saved receiver-calibration penalties.
"""

import json
from pathlib import Path

import numpy as np

from analyze import coordinates, error_vector


HERE = Path(__file__).resolve().parent
CASES = {
    'scan-fw-0695481606e1a3e8': 'Accurate saved mode loses to the tight timing prior',
    'scan-fw-6bf407cfe8158445': 'Free-c search misses a better saved zero-c solution',
    'scan-fw-559a822227a6a71b': 'Converged far-away solution with low signal responsibility',
    'scan-fw-e3bebc228093a125': 'Timeout and local-boundary solutions',
    'scan-fw-6a376b600fc2f542': 'Both methods wrong despite convergence and shared association',
}


def decompose(row, document):
    fit = row['fit']
    vector = np.asarray(fit['vector'])
    score = document['configuration']['scores'][row['method']]
    common = float(0.5 * (vector[7] / score['common_sigma_s']) ** 2)
    # Orthonormal zero-sum basis preserves the squared norm of relative shifts.
    relative = float(0.5 * np.sum((vector[8:] / score['relative_sigma_s']) ** 2))
    lat, lon = coordinates(*vector[:2])
    error = np.linalg.norm(error_vector(lat, lon, document['reference_latitude_deg'],
                                       document['reference_longitude_deg']))
    count = len(vector) - 7
    return {
        'method': row['method'], 'arm': row['arm'], 'basin': row['basin'],
        'horizontal_error_m': float(error), 'data_nll': fit['objective'] - common - relative,
        'common_timing_penalty': common, 'relative_timing_penalty': relative,
        'calibration_penalty': row['calibration_penalty'],
        'selection_score': fit['objective'] + row['calibration_penalty'],
        'relative_timing_rms_s': float(np.linalg.norm(vector[8:]) / np.sqrt(count)),
        'posterior_rms_hz': fit['posterior_rms_hz'],
        'signal_fraction': fit['signal_windows'] / document['windows'],
        'converged': fit['converged'], 'boundary': fit['boundary'],
        'stationarity': fit['stationarity'], 'stop_reason': fit['stop_reason'],
    }


def best(rows):
    return min(rows, key=lambda r: r['fit']['objective'] + r['calibration_penalty'])


def main():
    snapshot = json.loads((HERE / 'snapshot.json').read_text())
    gaps, cases = [], []
    for capture in snapshot['captures']:
        doc = capture.get('regional_document')
        if not doc:
            continue
        finals = [r for r in doc['diagnostics']['final_starts'] if r['fit']]
        for method in doc['methods']:
            free, zero = (arm['selected'] for arm in method['arms'])
            gap = free['selection_score'] - zero['selection_score']
            if gap > 1e-6:
                gaps.append(dict(session_id=capture['session_id'], method=method['name'],
                                 free_minus_zero_score=gap,
                                 free_error_m=free['horizontal_error_m'],
                                 zero_error_m=zero['horizontal_error_m']))
        if capture['session_id'] not in CASES:
            continue
        selected = {
            method['name']: {arm['name']: arm['selected'] for arm in method['arms']}
            for method in doc['methods']
        }
        t1_basin = selected['T1AT']['fitted-c']['source_basin']
        v16_free = [r for r in finals if r['method'] == 'V16' and r['arm'] == 'fitted-c']
        winner = best(v16_free)
        alternative = best([r for r in v16_free if r['basin'] == t1_basin])
        cases.append({
            'session_id': capture['session_id'], 'capture_start_utc': capture['capture_start_utc'],
            'diagnostic_label': CASES[capture['session_id']], 'selected': selected,
            'V16_fitted_winner': decompose(winner, doc),
            'V16_fitted_in_T1AT_basin': decompose(alternative, doc),
        })
    output = dict(snapshot_utc=snapshot['snapshot_utc'], cases=cases,
                  free_c_dominated_by_saved_zero_c=gaps,
                  limitations=[
                      'Saved-point decomposition only; no new optimizer run or causal mechanism validation.',
                      'Same matched per-basin starts/budgets and common observation inventory; calibration and satellite sets differ between basins.',
                      'Zero-c is feasible in the fitted-c model with identical objective and constraints at that same basin; better feasible score does not guarantee improved position after further optimization.',
                      'Posterior-weighted frequency RMS and signal responsibility are model-dependent diagnostics, not independent accuracy measures.',
                  ])
    (HERE / 'failure_cases.json').write_text(json.dumps(output, indent=2))
    print('Saved', len(cases), 'cases;', len(gaps), 'nested-model search gaps')


if __name__ == '__main__':
    main()
