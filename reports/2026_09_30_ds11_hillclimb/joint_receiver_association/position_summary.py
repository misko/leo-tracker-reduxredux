"""Unseal reference scoring only after all declared pilot fits are saved."""
import json
from pathlib import Path
import sys
import numpy as np
from doppler_pilot import digest, read

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / '2026_09_30_ds11_single10'))
from summarize import distance


def main():
    sources = {}
    rows = []
    arms = ('doppler', 'receiver', 'signed', 'swapped', 'permuted')
    for index in (0, 16):
        for arm in arms:
            assert (HERE / f'position-{index:02d}-{arm}.json').exists()
    for index in (0, 16):
        original_path = HERE.parent.parent / '2026_09_30_ds11_single10' / 'runs' / f'{index:02d}_iid.json'
        original = read(original_path)['selected']
        sources[str(original_path)] = digest(original_path)
        rows.append(dict(index=index, arm='original', distance_m=distance(original['estimate_deg']), qualified=True))
        bound = read(HERE / f'input-{index:02d}.json')
        for arm in arms:
            path = HERE / f'position-{index:02d}-{arm}.json'
            out = read(path)
            sources[str(path)] = digest(path)
            for p, h in out['sources'].items():
                assert digest(p) == h, p
            uncertain_edges = 0
            entropy = 0.
            pairs = []
            for lane, diagnostic in zip(bound['lanes'], out['lane_diagnostics']):
                p = np.array(diagnostic['pair_posterior'])
                uncertain_edges += int(((p > .01) & (p < .99)).sum())
                for i, tid in enumerate(lane['left']):
                    probs = np.r_[p[i], max(0., 1 - p[i].sum())]
                    probs = probs[probs > 0]
                    entropy -= float(np.sum(probs * np.log(probs)))
                    for j in np.flatnonzero(p[i] > .5):
                        pairs.append([tid, lane['right'][j]])
            rows.append(dict(index=index, arm=arm, distance_m=distance(out['coordinates_deg']), qualified=out['qualified'], training=out['score'], held=out['held_score'], expected_pairs=out['expected_pairs'], uncertain_edges=uncertain_edges, summed_left_assignment_entropy=entropy, majority_pairs=pairs, elapsed_s=out['elapsed_s']))
    table = {(r['index'], r['arm']): r for r in rows}
    passed = all(table[i, 'signed']['qualified'] and all(table[i, 'signed']['distance_m'] < table[i, a]['distance_m'] for a in ('original', 'doppler')) for i in (0, 16)) and np.median([table[i, 'signed']['distance_m'] for i in (0, 16)]) < np.median([table[i, 'receiver']['distance_m'] for i in (0, 16)])
    sources[str(Path(__file__))] = digest(Path(__file__))
    output = dict(rows=rows, primary_pilot_passed=bool(passed), sources=sources, limitations=['two previously examined development scans', 'single start per fit', 'conditional inferred detections, no clutter or full absence model', 'unsurveyed roof reference'])
    with (HERE / 'position-summary.json').open('x') as f:
        json.dump(output, f, indent=2, allow_nan=False)
    print(json.dumps(dict(rows=[{k: v for k, v in r.items() if k != 'majority_pairs'} for r in rows], passed=bool(passed)), indent=2))


if __name__ == '__main__':
    main()
