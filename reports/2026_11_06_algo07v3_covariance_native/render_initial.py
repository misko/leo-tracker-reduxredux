"""Summarize exact initial-branch precision calls without claiming a speedup."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile', type=Path, required=True)
    args = p.parse_args()
    root = Path(__file__).resolve().parent
    data = json.loads((args.profile/'result.json').read_bytes())
    assert data['exact']
    for name, digest in data['plan']['bindings'].items():
        choices = [Path(name)]
        if '/src/' in name:
            relative = name.split('/src/', 1)[1]
            choices += [root/side/relative for side in ('baseline-src', 'candidate-src')]
        assert any(q.exists() and hashlib.sha256(q.read_bytes()).hexdigest() == digest
                   for q in choices), name
    rows, duplicates = [], []
    for fit in data['results']:
        assert fit['exact']
        seen, repeated = {}, []
        for r in fit['calls']:
            key = r['input_signature']
            if key in seen:
                assert r['result_signature'] == seen[key]
                repeated.append(r)
            seen[key] = r['result_signature']
        duplicates.append(dict(arm=fit['arm'], calls=len(fit['calls']),
                               repeated_calls=len(repeated),
                               repeated_seconds=sum(r['seconds'] for r in repeated),
                               repeated_cpu_seconds=sum(r['cpu_seconds'] for r in repeated),
                               seconds=fit['seconds'], cpu_seconds=fit['cpu_seconds']))
        assert {r['phase'] for r in fit['calls']} == set(range(5))
        for phase in range(5):
            calls = [r for r in fit['calls'] if r['phase'] == phase]
            rows.append(dict(arm=fit['arm'], phase=phase, calls=len(calls),
                             mean_iterations=sum(r['iterations'] for r in calls)/len(calls),
                             capped=sum(r['iterations'] == 256 for r in calls),
                             unconverged=sum(r['final_change'] >= 1e-5 for r in calls),
                             seconds=sum(r['seconds'] for r in calls),
                             widths=sorted({r['width'] for r in calls})))
    (root/'initial-summary.json').write_text(json.dumps(dict(
        rows=rows, duplicates=duplicates, exact=True, measured_speedup=None), indent=2)+'\n')
    shutil.copyfile(args.profile/'result.json', root/'initial-profile.json')
    lines = ['| Arm | Phase | Calls | Mean precision iterations | At 256 | Unconverged | '
             'Likelihood seconds |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    lines.extend(f"| {r['arm']} | {r['phase']} | {r['calls']} | {r['mean_iterations']:.1f} | "
                 f"{r['capped']} | {r['unconverged']} | {r['seconds']:.3f} |" for r in rows)
    (root/'initial-phases.md').write_text('\n'.join(lines)+'\n')
    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout='constrained')
    for arm, offset in [('c0', -.2), ('fitted_c', .2)]:
        selected = [r for r in rows if r['arm'] == arm]
        for ax, field in zip(axes, ('seconds', 'mean_iterations'), strict=True):
            ax.bar([r['phase']+offset for r in selected], [r[field] for r in selected],
                   width=.4, label=arm)
    axes[0].set(ylabel='Summed likelihood seconds', xlabel='Phase round',
                title='Original calls, including final metrics')
    axes[1].set(ylabel='Mean precision iterations per call', xlabel='Phase round',
                title='Unchanged convergence policy')
    for ax in axes:
        ax.legend()
        ax.set_xticks(range(5))
    fig.savefig(root/'initial-convergence.png', dpi=150)
    plt.close(fig)
    print(json.dumps(duplicates, indent=2))


if __name__ == '__main__':
    main()
