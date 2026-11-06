"""Summarize all four completed native endpoint-reuse fit trials."""

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
    verified = json.loads((args.input / 'verified.json').read_bytes())
    assert verified['bindings_unchanged'] and verified['exact_complete_fit']
    plan = json.loads((args.input / 'plan.json').read_bytes())
    for name, sha in plan['bindings'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == sha, name
    rows = json.loads((args.input / 'result.json').read_bytes())['rows']
    assert len(rows) == 4 and all(r['exact'] for r in rows)
    groups = [[r for r in rows if r['side'] == side] for side in ('baseline', 'candidate')]
    wall = [mean(r['seconds'] for r in g) for g in groups]
    cpu = [mean(r['cpu_seconds'] for r in g) for g in groups]
    calls = groups[0][0]['calls']
    unique, repeated = set(), []
    for call in calls:
        key = (call['inputs'], call['optimize_contractions'])
        if key in unique:
            repeated.append(call)
        unique.add(key)
    summary = dict(wall_seconds=wall, cpu_seconds=cpu,
        wall_reduction_pct=100*(1-wall[1]/wall[0]),
        cpu_reduction_pct=100*(1-cpu[1]/cpu[0]),
        baseline_calls=len(calls), unique_inputs=len(unique), repeated_calls=len(repeated),
        repeated_kernel_seconds=sum(r['seconds'] for r in repeated),
        removed_final_kernel_seconds=calls[-1]['seconds'], full_pipeline_speedup=None)
    args.output.mkdir(exist_ok=False, parents=True)
    for path in args.input.iterdir():
        if path.is_file():
            shutil.copy2(path, args.output / path.name)
    for suffix in ('launch.json', 'terminal.json', 'worker.log'):
        shutil.copy2(Path(str(args.input) + '-' + suffix), args.output / suffix)
    shutil.copy2('tools/benchmark_algo07v3_final_joint.py', args.output / 'benchmark_source.py')
    (args.output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    fig, axes = plt.subplots(1, 2, figsize=(9, 4), constrained_layout=True)
    for ax, key, title in zip(axes, ('seconds', 'cpu_seconds'), ('Wall seconds', 'CPU seconds'),
                              strict=True):
        for a, b in ((rows[0], rows[1]), (rows[3], rows[2])):
            ax.plot([0, 1], [a[key], b[key]], 'o-', alpha=.7)
        ax.set_xticks([0, 1], ['Original', 'Endpoint reuse'])
        ax.set_ylabel(title)
        ax.grid(alpha=.2)
    fig.suptitle('Complete predictive c=0 joint fit: endpoint reuse\n'
                 'Two opposite-order pairs; complete results exact; no pipeline gain established')
    fig.savefig(args.output / 'runtime.png', dpi=150)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
