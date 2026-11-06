"""Verify the 0102 full profile and separate predictive/numerical stage costs."""

import argparse
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import matplotlib
from compare_algo07v3_runs import compare_science

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np


def read(path):
    return json.loads(path.read_bytes())


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--profile', type=Path, required=True)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    out = args.output
    out.mkdir(exist_ok=False)
    plan = read(args.profile / 'plan.json')
    assert plan['timers_only']
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == sha
               for p, sha in plan['bindings'].items())
    worker = read(args.profile / 'worker.json')
    assert worker['status'] == 'complete' and not worker['resumed']
    worker_rows = read(args.profile / 'worker-resources.json')
    assert len(worker_rows) == 1 and worker_rows[0]['completed']
    comparison = compare_science(SimpleNamespace(
        baseline_request=args.reference / 'request.json',
        candidate_request=args.profile / 'request.json',
        changed_module=[], added_module=[]))
    comparison.update(supervisor_receipt_available=(args.profile / 'profile.json').exists(),
                      clean_native_timing=False,
                      timing_scope='worker stage measurements only; supervisor was lost')
    (out / 'comparison.json').write_text(json.dumps(comparison, indent=2) + '\n')
    rows = read(args.profile / 'recovery-substages.json')
    assert all(r['completed'] and r['parent_stage'] for r in rows)
    selected = {stage: [r for r in rows if r['parent_stage'] == stage]
                for stage in ('predictive', 'numerical')}
    totals = {r['name']: r for r in read(args.profile / 'stage-resources.json')}
    summary = dict(stages=selected, totals=totals, worker_resources=worker_rows[0],
                   exact_owned_science_and_artifacts=True, qualified_speedup=None)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    ordered = sorted(selected['numerical'], key=lambda r: r['seconds'], reverse=True)
    table = '| Numerical substage | Wall s | Parent + child CPU s |\n| --- | ---: | ---: |\n'
    for r in ordered:
        table += (f"| {r['name']} | {r['seconds']:.3f} | "
                  f"{r['self_cpu_seconds'] + r['children_cpu_seconds']:.3f} |\n")
    (out / 'numerical-stages.md').write_text(table)
    names = [r['name'] for r in ordered[:14]][::-1]
    fig, ax = plt.subplots(figsize=(12, 8), layout='constrained')
    y = np.arange(len(names))
    for offset, stage in [(-.2, 'predictive'), (.2, 'numerical')]:
        values = {r['name']: r['seconds'] for r in selected[stage]}
        ax.barh(y + offset, [values.get(n, 0) for n in names], height=.4, label=stage)
    ax.set(yticks=y, yticklabels=names, xlabel='Profiled elapsed seconds',
           title='DS26-0102: numerical replay recomputes expensive joint work\n'
                 'Substages are contained in their parent stage; do not add both')
    ax.legend()
    fig.savefig(out / 'numerical-stages.png', dpi=150)
    plt.close(fig)
    print(json.dumps({stage: totals[stage]['seconds'] for stage in selected}))


if __name__ == '__main__':
    main()
