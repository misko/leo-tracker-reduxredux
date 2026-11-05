"""Verify and render the external posterior experiments without claiming pipeline speed."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--tests', type=Path, required=True)
    parser.add_argument('--name', choices=('assembly', 'variance'), required=True)
    args = parser.parse_args()
    result = json.loads((args.source / 'result.json').read_bytes())
    assert result['exact'] and all(r['exact'] for r in result['rows'])
    expected_count = 12 if args.name == 'assembly' else 8
    assert len(result['rows']) == expected_count
    report = Path(__file__).resolve().parent
    archived = {
        str(Path('src/leo/analysis/localization_v3/hierarchical.py').resolve()):
            Path('tools/algo07v3_preindex_hierarchical_oracle.py'),
        str(Path('tools/probe_algo07v3_posterior_assembly.py').resolve()):
            report / 'assembly/measured-benchmark-tool.txt',
        str(Path('tools/benchmark_algo07v3_training_kernel.py').resolve()):
            report / 'variance/measured-benchmark-tool.txt',
        str(Path('tools/probe_algo07v3_variance_indices.py').resolve()):
            report / 'variance/measured-prototype.txt',
    }
    for path, sha in result['bindings'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() == sha:
            continue
        # Keep measured bytes when a helper switches to the frozen baseline,
        # or the separately qualified candidate is integrated into runtime.
        assert path in archived, path
        assert hashlib.sha256(archived[path].read_bytes()).hexdigest() == sha, path
    if args.name == 'assembly':
        from probe_algo07v3_posterior_assembly import candidate_function
    else:
        from probe_algo07v3_variance_indices import candidate_function
    _, original, candidate = candidate_function()
    assert original == (args.source / 'original.txt').read_text()
    assert candidate == (args.source / 'candidate.txt').read_text()
    suites = list(ET.parse(args.tests).getroot().iter('testsuite'))
    assert not any(int(s.attrib[k]) for s in suites for k in ('errors', 'failures', 'skipped'))
    count = sum(int(s.attrib['tests']) for s in suites)
    assert count == (26 if args.name == 'assembly' else 28)
    out = Path(__file__).resolve().parent / args.name
    out.mkdir(exist_ok=True)
    for name in ('result.json', 'plan.json', 'original.txt', 'candidate.txt'):
        (out / name).write_bytes((args.source / name).read_bytes())
    if (args.source / 'benchmark-tool.py').exists():
        (out / 'measured-benchmark-tool.txt').write_bytes(
            (args.source / 'benchmark-tool.py').read_bytes())
    (out / 'tests.xml').write_bytes(args.tests.read_bytes())
    summary = dict(exact=True, tests=count, full_pipeline_speedup=None, runtime_modified=False,
                   means=result['means'])
    summary['change_percent'] = {
        arm: {key: 100 * (m['candidate'][key] / m['baseline'][key] - 1)
              for key in ('seconds', 'cpu_seconds')} for arm, m in result['means'].items()}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), layout='constrained')
    arms = ['c0', 'fitted_c']
    for ax, key in zip(axes, ('seconds', 'cpu_seconds'), strict=True):
        high = 0
        for side, offset, color in [('baseline', -.18, '#68778b'), ('candidate', .18, '#168579')]:
            means = [result['means'][a][side][key] for a in arms]
            bars = ax.bar(np.arange(2) + offset, means, width=.35, label=side, color=color)
            ax.bar_label(bars, labels=[f'{v:.3f}' for v in means], padding=3)
            for i, arm in enumerate(arms):
                values = [r[key] for r in result['rows'] if r['arm'] == arm and r['side'] == side]
                ax.scatter(np.full(len(values), i + offset), values, color='black', s=15, zorder=3)
                high = max(high, max(values))
        ax.set(xticks=[0, 1], xticklabels=['c = 0', 'Fitted c'], ylim=(0, high * 1.22),
               ylabel='Elapsed seconds' if key == 'seconds' else 'Process CPU seconds')
        ax.grid(axis='y', alpha=.2)
    axes[1].legend(loc='upper center', ncol=2)
    title = ('DS26-0002 · ordered posterior assembly · 12 exact five-round fits'
             if args.name == 'assembly'
             else 'DS26-0066 · covariance indices · 8 exact five-round training fits')
    fig.suptitle(title + '\nPrepared fits only; dots show individual trials')
    fig.savefig(out / 'timing.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
