"""Association changes are diagnostics, never verified label corrections."""
import json
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / 'acquisition_position'))
from common import JOBS, read, digest, verify_sources


def main():
    rows, tracks, sources = [], [], {str(Path(__file__)): digest(Path(__file__))}
    for c, i, family in JOBS:
        path = HERE / f'diagnostic-{c}-{i:02d}.json'
        doc = read(path)
        verify_sources(doc)
        sources[str(path)] = digest(path)
        row = dict(cohort=c, index=i, family=family, tracks=len(doc['reference']), models={})
        for name, model in doc['models'].items():
            probabilities = model['reference_probability']
            row['models'][name] = dict(qualified=model['qualified'], entropy_nats=model['entropy_nats'], expected_different_identities=model['expected_different_identities'], original_identity_lost_majority=sum(p < .5 for p in probabilities.values()), high_confidence_original_lost_majority=sum(doc['reference'][t]['original_probability'] >= .99 and p < .5 for t, p in probabilities.items()))
        rows.append(row)
        for tid, ref in doc['reference'].items():
            tracks.append(dict(cohort=c, index=i, track_id=tid, **ref, probabilities={name: model['reference_probability'][tid] for name, model in doc['models'].items()}))
    totals = {name: dict(expected_different_identities=sum(r['models'][name]['expected_different_identities'] for r in rows), original_identity_lost_majority=sum(r['models'][name]['original_identity_lost_majority'] for r in rows), high_confidence_original_lost_majority=sum(r['models'][name]['high_confidence_original_lost_majority'] for r in rows), entropy_nats=sum(r['models'][name]['entropy_nats'] for r in rows)) for name in ('doppler', 'joint', 'frozen')}
    result = dict(rows=rows, tracks=tracks, totals=totals, track_count=len(tracks), original_confident_tracks=sum(t['original_probability'] >= .99 for t in tracks), joint_frozen_probability_maximum_difference=max(abs(t['probabilities']['joint'] - t['probabilities']['frozen']) for t in tracks), sources=sources, scope='inferred probabilities on finite candidate banks; no verified satellite labels')
    with (HERE / 'summary.json').open('x') as f:
        json.dump(result, f, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in result.items() if k not in ('sources', 'tracks')}, indent=2))


if __name__ == '__main__':
    main()
