"""Census detector-to-track selection without geographic reference data."""
from collections import Counter
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def census(doc):
    used = {cid for t in doc['tracks'] for cid in t['candidate_ids']}
    counts = Counter()
    states = Counter()
    for o in doc['opportunities']:
        detection, retained = [], []
        for rx in ('rx0', 'rx1'):
            v = o['receivers'][rx]
            counts['views'] += 1
            counts[v['receiver_status']] += 1
            passing = [c for c in v['candidates'] if c['passed_fractional_margin_gate']]
            tracked = [c for c in passing if c['projected_candidate_id'] in used]
            detection.append(bool(passing))
            retained.append(bool(tracked))
            if passing and not tracked:
                counts['detected_but_no_retained_track'] += 1
            for c in v['candidates']:
                counts['candidates'] += 1
                counts['passing' if c['passed_fractional_margin_gate'] else 'rejected'] += 1
                if c['projected_candidate_id'] is not None:
                    counts['projected'] += 1
                if c['projected_candidate_id'] in used:
                    counts['retained'] += 1
                assert abs(c['fractional_exact_score'] - c['fractional_control_score'] - c['fractional_margin']) < 1e-9
        states[f"detector:{int(detection[0])}{int(detection[1])}/tracks:{int(retained[0])}{int(retained[1])}"] += 1
    return dict(counts=dict(counts), paired_states=dict(states))


def main():
    rows, sources = [], {}
    input_dir = HERE.parent / 'acquisition_position'
    for path in sorted([*input_dir.glob('input-original-*.json'), *input_dir.glob('input-additional-*.json')]):
        doc = json.loads(path.read_text())
        rows.append(dict(cohort=doc['cohort'], index=doc['index'], **census(doc)))
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(rows) == 11
    totals = Counter()
    for row in rows:
        totals.update(row['counts'])
    sources[str(Path(__file__))] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    result = dict(rows=rows, totals=dict(totals), sources=sources, scope='eleven stored pilot inputs; detection and retained track presence are distinct')
    with (HERE / 'census.json').open('x') as f:
        json.dump(result, f, indent=2)
    print(json.dumps(dict(totals=dict(totals))))


if __name__ == '__main__':
    main()
