"""Render the completed targeted profile; timings include profiling overhead."""
import argparse
import json
import pstats
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    args = parser.parse_args()
    dest = Path(__file__).resolve().parent
    for name in ('profile.json', 'parity.json', 'recovery-substages.json',
                 'plan.json', 'resources-start.json', 'resources-end.json'):
        (dest / name).write_bytes((args.source / name).read_bytes())
    children = []
    for path in sorted(args.source.glob('profile-*.json')):
        stats = pstats.Stats(str(path.with_suffix('.pstats')))
        row = json.loads(path.read_text())
        row['profile_file'] = path.with_suffix('.pstats').name
        row['profile_total_seconds'] = stats.total_tt
        row['top_self_time'] = [
            dict(file=key[0], line=key[1], function=key[2],
                 calls=value[1], self_seconds=value[2], cumulative_seconds=value[3])
            for key, value in sorted(stats.stats.items(),
                                     key=lambda item: item[1][2], reverse=True)[:10]
        ]
        children.append(row)
    (dest / 'children.json').write_text(json.dumps(children, indent=2) + '\n')
    # The first eight rows belong to predictive recovery. Later rows are
    # numerical replay/gap work and must not be counted as predictive time.
    rows = json.loads((dest / 'recovery-substages.json').read_text())[:8]
    assert [row['name'] for row in rows] == [
        'target-0-annotation', 'target-0-inclusion', 'target-0-audit',
        'target-1-annotation', 'target-1-inclusion', 'target-1-audit',
        'target-1-retry', 'target-1-retry-audit',
    ]
    fig, ax = plt.subplots(figsize=(10, 5.5), layout='constrained')
    values = [row['seconds'] for row in rows]
    bars = ax.barh([row['name'] for row in rows], values, color='#326ba8')
    ax.bar_label(bars, labels=[f'{v:.2f} s' for v in values], padding=4)
    ax.invert_yaxis()
    ax.set_xlim(0, max(values) * 1.2)
    ax.set_xlabel('Elapsed seconds, including profiler overhead')
    ax.set_title('DS26-0002 · ALGO07v3 predictive recovery\n'
                 '56.69 s total; unchanged science and all eight PNGs')
    ax.grid(axis='x', alpha=.2)
    fig.savefig(dest / 'predictive-stages.png', dpi=160)
    plt.close(fig)


if __name__ == '__main__':
    main()
