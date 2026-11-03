"""Combine the unchanged three-scan pilot and nine-scan expansion."""
import json
from pathlib import Path

import numpy as np

from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    names = ['calibrated-joint-v1-evaluation.json',
             'calibrated-joint-expansion-v1-evaluation.json',
             'candidate-joint-expansion-v1-evaluation.json']
    sources = {str(Path(__file__)): digest(__file__)}
    evaluations = []
    for name in names:
        path = HERE/name
        assert digest(path) == path.with_suffix('.sha256').read_text().strip()
        sources[str(path)] = digest(path)
        evaluations.append(json.loads(path.read_text()))
    combined = evaluations[0]['rows']+evaluations[1]['rows']
    units = json.loads((HERE/'split-expansion-fit-v1/sources.json').read_text())['units']
    candidates = [r for r in combined if r['arm'] == 'candidate']
    assert sorted(r['unit'] for r in candidates) == sorted(units)
    assert len(combined) == 24
    old = {r['unit']: r for r in evaluations[2]['rows'] if r['arm'] == 'candidate'}
    rows = []
    for r in candidates:
        assert old[r['unit']]['valid']
        rows.append(dict(unit=r['unit'], valid=r['valid'], failures=r['audit_errors'],
            original_all_data_error_m=r['all_data_baseline_error_m'],
            uncalibrated_joint_error_m=old[r['unit']]['error_m'],
            calibrated_joint_error_m=r['error_m'],
            runtime_s=r['runtime_s'], cpu_s=r['cpu_s']))
    valid = [r for r in rows if r['valid']]
    summaries = {}
    for label in ['original_all_data', 'uncalibrated_joint', 'calibrated_joint']:
        values = [r[label+'_error_m'] for r in valid]
        summaries[label] = dict(median_error_m=float(np.median(values)) if values else None,
            p90_error_m=float(np.percentile(values, 90)) if values else None,
            within1000m_of12=sum(v <= 1000 for v in values),
            within3000m_of12=sum(v <= 3000 for v in values))
    result = dict(planned=12, accepted=len(valid), all_arms_valid=sum(r['valid'] for r in combined),
        rows=rows, summaries=summaries,
        improved_over_uncalibrated=sum(r['calibrated_joint_error_m'] < r['uncalibrated_joint_error_m']
                                       for r in valid),
        improved_over_all_data=sum(r['calibrated_joint_error_m'] < r['original_all_data_error_m']
                                   for r in valid),
        median_warm_runtime_s=float(np.median([r['runtime_s'] for r in rows])),
        maximum_warm_runtime_s=max(r['runtime_s'] for r in rows),
        median_cpu_s=float(np.median([r['cpu_s'] for r in rows if r['cpu_s'] is not None])),
        source_sha256=sources,
        qualification='Same12exposed development scans;3pilot plus9new scans, no retries. '
        'Fixed identities, frozen excluded-dataset calibration. Warm refits omit cold acquisition '
        'and preprocessing. Former checking observations are now fitting data. No new uncertainty '
        'calibration or independent-recording result. Failures retained in denominators; '
        'quantiles and paired comparisons conditional on acceptance.')
    verify_sources(sources)
    path = HERE/'calibrated-joint-panel-v1.json'
    with path.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    path.with_suffix('.sha256').write_text(digest(path)+'\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ['source_sha256', 'rows']}, indent=2))


if __name__ == '__main__':
    main()
