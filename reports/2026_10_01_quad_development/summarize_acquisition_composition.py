"""Combine sealed single, pair and quad computational ablations for reporting."""
import json
from pathlib import Path

import numpy as np
from screen_seed_prefix import digest, sealed

HERE = Path(__file__).resolve().parent


def main():
    output = HERE / 'acquisition-composition-overview-v1.json'
    if output.exists():
        raise FileExistsError(output)
    stages = (
        ('Singles', 'S1', 'one-start-blas-cold-summary-v1.json'),
        ('Pairs', 'D1', 'one-start-blas-window-pair-summary-v1.json'),
        ('Quads', 'Q', 'one-start-blas-window-quad-summary-v1.json'),
    )
    panels, inputs = [], {}
    for title, suffix, filename in stages:
        path = HERE / filename
        summary = sealed(path)
        inputs[str(path)] = digest(path)
        for key in ('sources', 'inputs', 'frozen_sources_and_inputs'):
            for name, expected in summary[key].items():
                assert digest(name) == expected, name
        expected_units = [ds + '-B01-' + suffix for ds in ('DS9', 'DS10', 'DS11')]
        assert [row['unit'] for row in summary['rows']] == expected_units
        panels.append(dict(title=title, rows=summary['rows']))
    result = dict(
        panels=panels, inputs=inputs,
        sources={str(Path(__file__).resolve()): digest(Path(__file__).resolve())},
        qualification='Eighteen fresh inference outcomes on nine related development windows. '
        'Both arms use one start; only acquisition implementation changes. '
        'Inference excludes extraction, prerequisite checks and separate audits. '
        'One measurement per arm, fixed alternating orders, uncontrolled host/cache effects. '
        'No pooled independent-sample estimate or full-panel runtime claim.',
    )
    with output.open('x') as stream:
        json.dump(result, stream, indent=2, allow_nan=False)
    output.with_suffix('.sha256').write_text(digest(output) + '\n')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 3, figsize=(13, 7), constrained_layout=True)
    for column, panel in enumerate(panels):
        rows = panel['rows']
        for arm, label, offset, color in (
            ('original', 'Original acquisition', -.18, 'tab:blue'),
            ('blas', 'Optimized acquisition', .18, 'tab:orange'),
        ):
            for index, row in enumerate(rows):
                outcome = row['arms'][arm]
                x = index + offset
                axes[0, column].bar(x, outcome['wall_seconds'], .36,
                                    label=label if index == 0 else None, color=color)
                if outcome['accepted']:
                    axes[1, column].bar(x, outcome['error_m'], .36, color=color)
                else:
                    axes[1, column].text(x, 0, 'failed', rotation=90, ha='center')
        axes[0, column].set_title(panel['title'])
        for row_index in (0, 1):
            axes[row_index, column].set_xticks(np.arange(3), ['DS9', 'DS10', 'DS11'])
            axes[row_index, column].grid(axis='y', alpha=.2)
        axes[0, column].set_ylabel('Inference wall time (s)')
        axes[1, column].set_ylabel('Accepted reference error (m)')
    axes[0, 0].legend(fontsize=9)
    fig.suptitle('One-start policy fixed: acquisition implementation comparison')
    fig.savefig(output.with_suffix('.png'), dpi=160)
    print(json.dumps(dict(windows=sum(len(p['rows']) for p in panels),
                         all_equivalent=all(r['both_accepted_equivalent']
                                            for p in panels for r in p['rows']))))


if __name__ == '__main__':
    main()
