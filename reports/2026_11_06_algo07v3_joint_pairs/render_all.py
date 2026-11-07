"""Show every predeclared native pair, including regressions and inactive control."""

import argparse
import json
from pathlib import Path

from render_native import summarize


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--first', type=Path, required=True)
    parser.add_argument('--reverse', type=Path, required=True)
    parser.add_argument('--control', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    cases = [('DS26-0102, serial first', args.first, ['baseline', 'candidate']),
             ('DS26-0102, paired first', args.reverse, ['candidate', 'baseline']),
             ('DS26-0002, inactive control', args.control, ['candidate', 'baseline'])]
    results = []
    manifests = None
    active_request = None
    for label, root, order in cases:
        plan = json.loads((root / 'plan.json').read_bytes())
        terminal = json.loads(Path(str(root) + '-terminal.json').read_bytes())
        assert terminal['returncode'] == 0
        assert plan['sequence'] == order
        assert (plan['cpus'], plan['blas_threads'], plan['timeout_seconds']) == ([0, 1, 2], 1, 1200)
        sources = [json.loads((root / f'{side}-sources.json').read_bytes())
                   for side in ('baseline', 'candidate')]
        if manifests is None:
            manifests = sources
        assert sources == manifests, 'Runtime changed between predeclared pairs'
        requests = [json.loads((root / f'{side}-request.json').read_bytes())
                    for side in ('baseline', 'candidate')]
        for request in requests:
            del request['output_root']
        assert requests[0] == requests[1]
        if root == args.first:
            active_request = requests[0]
        if root == args.reverse:
            assert requests[0] == active_request, 'Reverse comparison must use the same scan/config'
        result = summarize(root.resolve())
        result.update(label=label, sequence=order)
        results.append(result)
    args.output.mkdir(exist_ok=False)
    (args.output / 'summary.json').write_text(json.dumps(results, indent=2) + '\n')
    table = ['| Case / order | Serial wall | Paired wall | Wall change | Serial CPU | '
             'Paired CPU | CPU change |', '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for result in results:
        before, after = (result['sides'][key] for key in ('baseline', 'candidate'))
        table.append(f"| {result['label']} | {before['seconds']:.3f} s | "
                     f"{after['seconds']:.3f} s | {-result['wall_reduction_percent']:+.2f}% | "
                     f"{before['cpu_seconds']:.2f} s | {after['cpu_seconds']:.2f} s | "
                     f"{-result['cpu_reduction_percent']:+.2f}% |")
    table.append('\nPositive change means slower/more CPU. These are separate full runs; '
                 'scoped fit/audit clocks are not added or multiplied into these results.\n')
    (args.output / 'timings.md').write_text('\n'.join(table))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    figure, axes = plt.subplots(1, 2, figsize=(13, 5.8))
    x = np.arange(len(results))
    for axis, key, title in zip(axes, ('seconds', 'cpu_seconds'),
                               ('Complete elapsed time', 'CPU including descendants'),
                               strict=True):
        for index, (side, name, color) in enumerate(
                [('baseline', 'Serial fits', '#777777'),
                 ('candidate', 'Paired fits', '#3465a4')]):
            values = [result['sides'][side][key] for result in results]
            bars = axis.bar(x + (index - .5) * .36, values, .36, label=name, color=color)
            axis.bar_label(bars, fmt='%.1f', padding=3, fontsize=9)
        axis.set(xticks=x, xticklabels=['0102\nserial first', '0102\npaired first',
                                       '0002\ninactive control'], ylabel='Seconds', title=title)
        axis.set_ylim(0, axis.get_ylim()[1] * 1.12)
        axis.legend()
    figure.suptitle('ALGO07v3 paired joint fits · all predeclared native comparisons')
    figure.text(.5, .025, 'Exact science, both calibration arms and all eight PNGs. '
                'Shared host; no timing normalization.\n'
                'Native GLRT ready through publication; '
                'capture, GLRT extraction and queue excluded.',
                ha='center', fontsize=9)
    figure.tight_layout(rect=(0, .085, 1, .95))
    figure.savefig(args.output / 'runtime.png', dpi=160)
    plt.close(figure)
    print('\n'.join(table))


if __name__ == '__main__':
    main()
