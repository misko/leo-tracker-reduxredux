"""Render the completed DS26-0066 predictive profile and its exactness receipts."""
import argparse
import hashlib
import json
import pstats
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    dest = Path(__file__).resolve().parent
    profile = json.loads((args.source / 'profile.json').read_text())
    parity = json.loads((args.source / 'parity.json').read_text())
    assert profile['process']['returncode'] == 0 and not profile['changed_sources']
    assert profile['worker']['status'] == 'complete' and not profile['worker']['resumed']
    assert parity['profile_science_and_eight_pngs_exact']
    assert parity['shared_implementation_exact'] and parity['entry_point_bytes_identical']
    for path, sha in parity['bindings'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha
    for name in ('profile.json', 'parity.json', 'recovery-substages.json', 'plan.json',
                 'resources-start.json', 'resources-end.json'):
        (dest / name).write_bytes((args.source / name).read_bytes())
    children = []
    for path in sorted(args.source.glob('profile-*.json')):
        stats = pstats.Stats(str(path.with_suffix('.pstats')))
        row = json.loads(path.read_text())
        row.update(profile_file=path.with_suffix('.pstats').name,
                   profile_sha256=hashlib.sha256(path.with_suffix('.pstats').read_bytes()).hexdigest(),
                   profile_total_seconds=stats.total_tt)
        row['top_self_time'] = [dict(file=k[0], line=k[1], function=k[2], calls=v[1],
                                    self_seconds=v[2], cumulative_seconds=v[3])
                               for k, v in sorted(stats.stats.items(),
                                                  key=lambda item: item[1][2], reverse=True)[:10]]
        row['training_calls'] = [dict(file=k[0], function=k[2], calls=v[1],
                                     cumulative_seconds=v[3])
                                for k, v in stats.stats.items()
                                if k[2] in ('fit_training', 'hierarchical_bound', 'posterior')]
        children.append(row)
    (dest / 'children.json').write_text(json.dumps(children, indent=2) + '\n')
    all_rows = json.loads((args.source / 'recovery-substages.json').read_text())
    # Later rows are numerical replay and must not be counted again.
    split = next(i for i, r in enumerate(all_rows) if r['name'] == 'inventory')
    rows = all_rows[:split]
    assert len(rows) == 16 and rows[-1]['name'] == 'target-7-audit'
    predictive = next(r['seconds'] for r in profile['stages'] if r['stage'] == 'predictive')
    totals = {kind: sum(r['seconds'] for r in rows if r['name'].endswith(kind))
              for kind in ('annotation', 'inclusion', 'audit')}
    heavy = max(children, key=lambda r: r['profile_total_seconds'])
    summary = dict(predictive_seconds=predictive, substage_seconds=totals,
                   remaining_seconds=predictive - sum(totals.values()),
                   heavy_fold=heavy, profiled=True, speedup_claim=False,
                   native_through_publication_seconds=profile['process']['process_seconds'],
                   exact_science_and_eight_pngs=True)
    (dest / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    fig, axes = plt.subplots(1, 2, figsize=(13, 6), layout='constrained')
    names = [r['name'].removeprefix('target-') for r in rows]
    values = [r['seconds'] for r in rows]
    bars = axes[0].barh(names, values, color='#326ba8')
    axes[0].bar_label(bars, labels=[f'{v:.1f}' for v in values], padding=3, fontsize=8)
    axes[0].invert_yaxis()
    axes[0].set_xlim(0, max(values) * 1.2)
    axes[0].set_title('Predictive substages · nested inside 327.73 s')
    axes[0].set_xlabel('Profiled elapsed seconds')
    annotation = [r for r in children if r['stage'].endswith('-annotation')]
    seeds = sorted({r['item'] for r in annotation})
    colors = plt.get_cmap('tab10')
    for i, r in enumerate(annotation):
        axes[1].barh(i, r['profile_total_seconds'], color=colors(seeds.index(r['item']) % 10))
    axes[1].set_yticks(range(len(annotation)),
                      [f"{r['stage'].split('-')[1]} / {r['item']}" for r in annotation], fontsize=7)
    axes[1].invert_yaxis()
    axes[1].set_title('Individual annotation children · target / seed')
    axes[1].set_xlabel('Child profile total seconds; concurrent, not additive wall time')
    fig.suptitle('DS26-0066 · unchanged ALGO07v3 predictive profile\n'
                 'Exact science, both calibration arms and all eight PNG bytes')
    for ax in axes:
        ax.grid(axis='x', alpha=.2)
    fig.savefig(dest / 'predictive.png', dpi=150)
    plt.close(fig)
    print(json.dumps({k: v for k, v in summary.items() if k != 'heavy_fold'}, indent=2))


if __name__ == '__main__':
    main()
