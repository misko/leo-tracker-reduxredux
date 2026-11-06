"""Verify and publish current posterior profiling and rejected optimization evidence."""

import argparse
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from check_algo07v3_scan_likelihood import fingerprint
from probe_algo07v3_posterior_buffers import candidate_function
from probe_algo07v3_upper_triangular import reference, solve_upper


def read(path):
    return json.loads(path.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--profile', type=Path, required=True)
    parser.add_argument('--training', type=Path, required=True)
    parser.add_argument('--tests', type=Path, required=True)
    args = parser.parse_args()
    out = Path(__file__).resolve().parent
    kernel, profile, training = (read(args.kernel / 'result.json'),
                                 read(args.profile / 'profile.json'),
                                 read(args.training / 'result.json'))
    assert kernel['complete'] and profile['exact'] and training['exact']
    assert len(training['rows']) == 8 and all(r['exact'] for r in training['rows'])
    for arm in ('c0', 'fitted_c'):
        assert [r['side'] for r in training['rows'] if r['arm'] == arm] == [
            'baseline', 'candidate', 'candidate', 'baseline']
    for record in (kernel, profile, training):
        for path, sha in record['bindings'].items():
            actual = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            if actual != sha:
                assert Path(path).resolve() == Path(
                    'tools/probe_algo07v3_posterior_buffers.py').resolve(), path
                assert hashlib.sha256((out / 'measured' / Path(path).name).read_bytes()
                                      ).hexdigest() == sha
    for name in ('metadata', 'buffers', 'combined'):
        _, original, candidate = candidate_function(name)
        assert original == (args.kernel / 'original.py').read_text()
        assert candidate == (args.kernel / f'{name}.py').read_text()
    assert candidate_function('buffers')[2] == (args.training / 'candidate.py').read_text()
    suites = list(ET.parse(args.tests).getroot().iter('testsuite'))
    assert sum(int(s.attrib['tests']) for s in suites) == 94
    assert not any(int(s.attrib[k]) for s in suites for k in ('errors', 'failures', 'skipped'))
    for root, folder, names in (
            (args.kernel, 'kernel', ['plan.json', 'result.json', 'original.py',
                                    'metadata.py', 'buffers.py', 'combined.py']),
            (args.profile, 'profile', ['plan.json', 'profile.json', 'hardest.json',
                                      'training.pstats']),
            (args.training, 'training', ['plan.json', 'result.json', 'original.py',
                                        'candidate.py'])):
        dest = out / folder
        dest.mkdir(exist_ok=True)
        for name in names:
            (dest / name).write_bytes((root / name).read_bytes())
    (out / 'tests.xml').write_bytes(args.tests.read_bytes())
    rejection = []
    for n in (3, 175):
        rng = np.random.default_rng(101)
        a = rng.normal(size=(n, n))
        upper = np.linalg.cholesky(a @ a.T + np.eye(n)).T
        rhs = np.full(n, -0.)
        before = reference._solve_factor(upper, np.arange(n, dtype=np.int32), rhs)
        after = solve_upper(upper, rhs)
        assert fingerprint(before) != fingerprint(after)
        rejection.append(dict(width=n, input=fingerprint((upper, rhs)),
                              baseline=fingerprint(before), candidate=fingerprint(after)))
    (out / 'upper-solve-rejection.json').write_text(json.dumps(rejection, indent=2) + '\n')
    counts = [r['precision_iterations'] for r in profile['calls']]
    summary = dict(profile_seconds=profile['result']['seconds'], calls=len(counts),
                   at_iteration_limit=sum(v == 256 for v in counts),
                   precision_iterations=sum(counts), means=training['means'],
                   exact_training_fits=8, tests=94, runtime_modified=False,
                   production_modified=False, qualified_speedup=None,
                   decision='Keep all experiments external')
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout='constrained')
    rows = profile['functions'][:6][::-1]
    labels = [r['function'].replace('<method ', '').replace(' of ', '\nof ') for r in rows]
    axes[0].barh(labels, [r['self_seconds'] for r in rows], color='#456990')
    axes[0].set(xlabel='Exclusive profiled seconds', title='Current slow c=0 training fit')
    axes[1].hist(counts, bins=[0, 32, 64, 96, 128, 160, 192, 224, 257], color='#49a078')
    axes[1].set(xlabel='Precision iterations per likelihood call', ylabel='Calls',
                title=f'{sum(v == 256 for v in counts)} of {len(counts)} reach 256')
    fig.suptitle('DS26-0066 · target 1 / fold 1 · full fit and history exact')
    fig.savefig(out / 'profile.png', dpi=160)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout='constrained')
    for ax, arm in zip(axes, ('c0', 'fitted_c'), strict=True):
        for side, offset, color in [('baseline', -.18, '#68778b'),
                                     ('candidate', .18, '#168579')]:
            rows = [r for r in training['rows'] if r['arm'] == arm and r['side'] == side]
            bars = ax.bar([r['pair'] + offset for r in rows],
                          [r['seconds'] for r in rows], width=.35, label=side, color=color)
            ax.bar_label(bars, fmt='%.2f', padding=3)
        ax.set(xticks=[0, 1], xticklabels=['B → C', 'C → B'], ylim=(0, 80),
               ylabel='Complete prepared training seconds', title=arm)
        ax.grid(axis='y', alpha=.2)
    axes[1].legend()
    fig.suptitle('Posterior scratch buffers · all eight fits exact\n'
                 'No demonstrated runtime gain; candidate remains external')
    fig.savefig(out / 'training.png', dpi=160)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
