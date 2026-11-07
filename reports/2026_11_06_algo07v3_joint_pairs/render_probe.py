"""Render every scoped paired-fit trial after verification, without timing normalization."""

import argparse
import hashlib
import json
import shutil
from pathlib import Path
from statistics import mean

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    plan = json.loads((args.input / 'plan.json').read_bytes())
    verified = json.loads((args.input / 'verified.json').read_bytes())
    assert verified['bindings_unchanged'] and verified['exact_complete_fit']
    assert plan['scope'] == 'both native joint-fit arms; audits excluded'
    for name, sha in plan['bindings'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha, name
    rows = json.loads((args.input / 'result.json').read_bytes())['rows']
    assert [r['side'] for r in rows] == ['baseline', 'candidate', 'candidate', 'baseline']
    assert all(r['exact'] and len(r['arm_signatures']) == 2 for r in rows)
    assert all((r['result'], r['arm_signatures'], r['policy_before'], r['policy_after']) == (
        rows[0]['result'], rows[0]['arm_signatures'], rows[0]['policy_before'],
        rows[0]['policy_after']) for r in rows)
    terminal = json.loads(Path(str(args.input) + '-terminal.json').read_bytes())
    assert terminal['returncode'] == 0
    groups = [[r for r in rows if r['side'] == side] for side in ('baseline', 'candidate')]
    wall = [mean(r['seconds'] for r in group) for group in groups]
    cpu = [mean(r['cpu_seconds'] for r in group) for group in groups]
    summary = dict(wall_seconds=wall, cpu_seconds=cpu,
        wall_reduction_pct=100 * (1-wall[1]/wall[0]),
        cpu_reduction_pct=100 * (1-cpu[1]/cpu[0]), full_pipeline_speedup=None,
        stage=plan['stage'], scope=plan['scope'])
    args.output.mkdir(exist_ok=False, parents=True)
    for source in args.input.iterdir():
        if source.is_file():
            shutil.copy2(source, args.output / source.name)
    for suffix in ('launch.json', 'terminal.json', 'worker.log'):
        shutil.copy2(Path(str(args.input) + '-' + suffix), args.output / suffix)
    for tool in ('benchmark_algo07v3_joint_pair.py', 'benchmark_algo07v3_final_joint.py'):
        shutil.copy2(Path('tools') / tool, args.output / tool)
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    fig, axes = plt.subplots(1, 2, figsize=(10, 4), constrained_layout=True)
    for ax, key, title in zip(axes, ('seconds', 'cpu_seconds'), ('Wall seconds', 'CPU seconds'),
                              strict=True):
        for label, a, b in (('Baseline first', rows[0], rows[1]),
                            ('Candidate first', rows[3], rows[2])):
            ax.plot([0, 1], [a[key], b[key]], 'o-', label=label)
        ax.set_xticks([0, 1], ['Serial fits', 'Two-process fits'])
        ax.set_ylabel(title)
        ax.grid(alpha=.2)
        ax.legend()
    fig.suptitle(f"Actual {plan['stage']} joint fits, both calibration arms\n"
                 'Opposite-order pairs; exact results; audits and publication excluded')
    fig.savefig(args.output / 'runtime.png', dpi=150)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
