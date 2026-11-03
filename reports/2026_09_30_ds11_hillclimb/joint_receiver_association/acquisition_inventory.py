"""Full acquisition-setting coverage, selected by metadata and chronology only."""
from collections import defaultdict
import json
from pathlib import Path
from doppler_pilot import read, digest

HERE = Path(__file__).resolve().parent
REPORTS = HERE.parent.parent


def key(observations):
    return observations['sample_rate_hz'], tuple(sorted({t['rf_hz'] for t in observations['tracks']}))


def main():
    paths = dict(ds10=REPORTS / '2026_09_30_ds10_scale_weighting/plan.json', original=REPORTS / '2026_09_30_ds11_single10/plan.json', additional=HERE.parent / 'additional/plan.json')
    manifest_path = REPORTS / '2026_09_29_ds10_post_ds9/local/manifest.json'
    captures = {r['session_id']: r for r in read(manifest_path)['captures']}
    sources = {str(p): digest(p) for p in (*paths.values(), manifest_path, Path(__file__))}
    groups = defaultdict(lambda: dict(ds10=[], original=[], additional=[]))
    starts = []
    for cohort, path in paths.items():
        for index, entry in enumerate(read(path)['inputs']):
            artifact = next(a for a in entry['artifacts'] if a['kind'] == 'observations')
            assert digest(artifact['path']) == artifact['sha256'].removeprefix('sha256:')
            sources[artifact['path']] = digest(artifact['path'])
            obs = read(artifact['path'])
            row = dict(index=index, session_id=entry['session_id'], start_utc_ns=obs['start_utc_ns'])
            if cohort == 'ds10':
                capture = captures[entry['session_id']]
                row.update(capture_end_utc_ns=capture['capture_end_utc_ns'], finalized_utc_ns=capture['finalized_utc_ns'], radio_id=capture['radio_id'])
            else:
                starts.append(obs['start_utc_ns'])
            groups[key(obs)][cohort].append(row)
    cutoff = min(starts)
    rows = []
    for number, (setting, cohorts) in enumerate(sorted(groups.items())):
        donors = sorted(cohorts['ds10'], key=lambda r: (r['capture_end_utc_ns'], r['index']))
        usable = [r for r in donors if r['capture_end_utc_ns'] < cutoff and r['finalized_utc_ns'] < cutoff and r['radio_id'] == 'radio_pluto_5d4d']
        split = (len(usable) + 1) // 2
        rows.append(dict(family=number, sample_rate_hz=setting[0], rf_hz=setting[1], calibration=usable[:split], validation=usable[split:], excluded_donors=[r for r in donors if r not in usable], original=cohorts['original'], additional=cohorts['additional'], has_separate_donor_validation=len(usable) >= 2))
    output = dict(families=rows, earliest_target_utc_ns=cutoff, sources=sources, selection='exact sample rate/RF, donor availability and hardware; chronological halves, no reference errors', calibration_or_fits_performed=False)
    with (HERE / 'acquisition-calibration-inventory.json').open('x') as f:
        json.dump(output, f, indent=2, allow_nan=False)
    print(json.dumps([dict(family=r['family'], rate=r['sample_rate_hz'], calibration=[d['index'] for d in r['calibration']], validation=[d['index'] for d in r['validation']], original=[d['index'] for d in r['original']], additional=[d['index'] for d in r['additional']]) for r in rows], indent=2))


if __name__ == '__main__':
    main()
