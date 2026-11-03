"""Verify results and compare joint refits without reference-based selection."""
import hashlib
import json
from pathlib import Path

from run import HERE, REPORTS, module, read


def main():
    diagnostic = read(HERE/'results.json')
    refits = [read(HERE/f'refit_{arm}.json') for arm in ['old', 'rank']]
    for result in [diagnostic]+refits:
        for name, digest in result['hashes'].items():
            assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == digest, name
    geometry = module('union_summary', REPORTS/'2026_09_29_ds8_union40/summarize.py')
    assert len(diagnostic['rows']) == 40
    valid = [r for r in refits if r['fit']['qualified']]
    assert valid
    selected = max(valid, key=lambda r:r['fit']['score'])
    rows = []
    for result in refits:
        arm = result['arm']
        prior = read(REPORTS/'2026_09_29_ds8_union40'/f'{arm}.json')
        if not result['fit']['qualified']:
            rows.append(dict(arm=arm, qualified=False, message=result['fit']['message'],
                             projected_gradient=result['fit']['projected_gradient'],
                             gradient_audit=result['fit']['gradient_audit'],
                             elapsed_seconds=result['elapsed_seconds']))
            continue
        rows.append(dict(arm=arm, reference_distance_m=geometry.distance(result['fit']['estimate_deg'], geometry.REFERENCE),
                         qualified=True,
                         endpoint_shift_m=geometry.distance(result['fit']['estimate_deg'], prior['fit']['estimate_deg']),
                         training_gain=result['fit']['score']-prior['fit']['score'],
                         held_gain=result['fit']['held_score']-prior['fit']['held_score'],
                         elapsed_seconds=result['elapsed_seconds']))
    attempts = [s for r in diagnostic['rows'] for a in r['arms'].values() for s in a['starts']]
    summary = dict(selected_arm=selected['arm'], refits=rows,
                   endpoint_gap_m=geometry.distance(*[r['fit']['estimate_deg'] for r in refits]) if len(valid)==2 else None,
                   timing_starts=len(attempts), qualified_timing_starts=sum(s['qualified'] for s in attempts),
                   timing_summary=diagnostic['summary'])
    (HERE/'summary.json').write_text(json.dumps(summary, indent=2, allow_nan=False)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
