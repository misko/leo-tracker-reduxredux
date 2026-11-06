"""Collect completed perf/coupling receipts and render scope-labelled evidence."""

import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main():
    output = Path(__file__).resolve().parent
    base = Path('/srv/bulk/leo-dev')
    summaries = {}
    for name in ('initial', 'recovery'):
        root = base/f'algo07v3-{name}-coupling-20261106'
        data = json.loads((root/'result.json').read_bytes())
        assert data['exact_transition_count'] == 256 and data['unchanged_inputs']
        digest = hashlib.sha256((root/'jacobians.npz').read_bytes()).hexdigest()
        assert digest == data['jacobians_sha256']
        for filename in ('result.json', 'jacobians.npz', 'generated.py', 'original.py'):
            (output/f'{name}-{filename}').write_bytes((root/filename).read_bytes())
        summaries[name] = data
    inactive = base/'algo07v3-inactive-columns-20261106'
    for filename in ('result.json', 'original.py', 'generated.py'):
        (output/f'inactive-{filename}').write_bytes((inactive/filename).read_bytes())
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    for ax, (name, data) in zip(axes, summaries.items(), strict=True):
        indices = sorted({r['iteration'] for r in data['results']})
        for j, epsilon in enumerate((1e-3, 3e-4, 1e-4)):
            values = [r['spectral_radius'] for r in data['results'] if r['epsilon']==epsilon]
            ax.scatter(np.arange(2)+(.05*(j-1)), values, label=f'Perturbation {epsilon:g}')
        ax.axhline(1, color='red', linestyle='--', label='Unit sensitivity')
        ax.set_xticks([0,1], [f'Iteration {i}' for i in indices])
        ax.set(title=name.title()+' likelihood', ylabel='Largest local eigenvalue magnitude')
        ax.grid(alpha=.2)
        ax.legend(fontsize=8)
    fig.suptitle('Original noise-precision map: nearly neutral, then locally expanding\n'
                 '512 saved transitions reproduced exactly; inference unchanged')
    fig.savefig(output/'coupling.png', dpi=150)
    plt.close(fig)
    native = base/'algo07v3-perf-native-0066-r2-20261106'
    result = json.loads((native/'result.json').read_bytes())
    assert result['scientific_equality']
    assert json.loads((native/'binding-check.json').read_bytes())['changed'] == []
    for filename in ('plan.json', 'request.json', 'inheritance.json', 'binding-check.json',
                     'result.json', 'comparison.json', 'native-counters.jsonl',
                     'native-execution.json', 'native-command.json'):
        (output/f'perf-{filename}').write_bytes((native/filename).read_bytes())
    for filename in ('supervisor.json', 'worker.json', 'worker.log'):
        (output/f'native-{filename}').write_bytes((native/'native/attempt'/filename).read_bytes())
    failed = base/'algo07v3-perf-native-0066-20261106'
    for filename in ('plan.json','child-excluded-command.json','child-excluded-counters.jsonl',
                     'child-excluded-execution.json'):
        (output/f'failed-{filename}').write_bytes((failed/filename).read_bytes())
    native_supervisor = json.loads((output/'native-supervisor.json').read_bytes())
    summary = dict(coupling={name:[dict(iteration=r['iteration'], epsilon=r['epsilon'],
                                      spectral_radius=r['spectral_radius'])
                                  for r in d['results']] for name,d in summaries.items()},
                   hardware=result['measured'], native_supervisor=native_supervisor,
                   exact=True, runtime_modified=False, full_pipeline_speedup=None)
    (output/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
