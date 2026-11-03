import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    summaries = []
    for ds in ('DS7', 'DS8', 'DS9'):
        assert json.loads((HERE / f'{ds}.receipt.json').read_text())['exit_code'] == 0
        data = json.loads((HERE / f'{ds}.json').read_text())
        summaries.extend(p['summary'] for p in data['panels'])
    assert len(summaries) == 18
    for r in summaries:
        assert r['tracks'] == r['stable_support']
        assert abs(r['training_gain'] - r['frozen_gain'] - r['posterior_kl']) < 1e-7
    table = ['| DS | Panel | Tracks | Training gain | Fixed-probability term | Probability-change term (KL) | Top component changes |', '|---|---|---:|---:|---:|---:|---:|']
    for r in summaries:
        table.append(f"| {r['dataset']} | {r['family']} {r['panel']} | {r['tracks']} | {r['training_gain']:.2f} | {r['frozen_gain']:.2f} | {r['posterior_kl']:.2f} | {r['top_component_changes']} |")
    (HERE / 'table.md').write_text('\n'.join(table) + '\n')
    with (HERE / 'summary.json').open('x') as out:
        json.dump(dict(rows=summaries, track_comparisons=sum(r['tracks'] for r in summaries), max_identity_error=max(r['max_identity_error'] for r in summaries), max_score_replay=max(max(r['panel_replay'],r['pooled_replay']) for r in summaries)), out, indent=2)
    for name, h in json.loads((HERE / 'manifest.json').read_text())['hashes'].items():
        assert hashlib.sha256((HERE.parents[1] / name).read_bytes()).hexdigest() == h
    print('Panels', len(summaries), 'track comparisons', sum(r['tracks'] for r in summaries), 'max identity error', max(r['max_identity_error'] for r in summaries), 'max replay', max(max(r['panel_replay'],r['pooled_replay']) for r in summaries))


if __name__ == '__main__':
    main()
