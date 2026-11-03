"""Collect measured receipts and render the runtime comparison without selecting runs."""

import hashlib
import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path('/srv/bulk/leo/research/algo07-runtime-20261103')
OUT = Path(__file__).resolve().parent


def main():
    receipts = OUT/'receipts'
    receipts.mkdir(exist_ok=True)
    sources = {
        'prepared-parity.json': ROOT/'algo03-fresh/full-scientific-parity-v2.json',
        'hierarchical-parity.json': ROOT/'algo03-fresh/hierarchical-scientific-parity.json',
        'repeat-parity.json': ROOT/'algo03-fresh/hierarchical-repeat-parity.json',
        'likelihood-timings.json': ROOT/'hierarchical-prepared-timing.json',
        'triangular-experiment.json': ROOT/'hierarchical-triangular-timing.json',
        'saved-policy-parity.json': ROOT/'hierarchical-policy-parity.json',
        'population-parity.json': ROOT/'population/hierarchical-runtime-parity.json',
        'algo07-fresh-parity.json': ROOT/'fresh-fallback/hierarchical-parity.json',
        'algo07-fresh-timing.json': ROOT/'fresh-fallback/replay-hierarchical/timing.json',
        'algo07-fresh-audit.json': ROOT/'fresh-fallback/replay-hierarchical/read-audit.json',
    }
    trials = ('baseline', 'prepared-candidate', 'hierarchical-candidate', 'baseline-repeat')
    measurements = []
    for name in trials:
        folder = ROOT/'algo03-fresh'/name
        sources[name+'-timing.json'] = folder/'timing.json'
        timing = json.loads((folder/'timing.json').read_text())
        launch = json.loads((folder/'launch.json').read_text())
        stages = {p.stem.removesuffix('-receipt'): json.loads(p.read_text())
                  for p in (folder/'worker/recovery').glob('*receipt.json')}
        measurements.append(dict(name=name, timing=timing, load_average=launch['load_average'],
                                 stages={k: v['seconds'] for k, v in stages.items()}))
    for name, path in sources.items():
        shutil.copyfile(path, receipts/name)
    for name in ('launch.json', 'sampling.json', 'sampler.log', 'stacks.folded'):
        shutil.copyfile(ROOT/'hierarchical-inclusion-sample'/name, receipts/('sample-'+name))
    capture = OUT/'likelihood-inputs'
    shutil.copytree(ROOT/'hierarchical-fresh-capture', capture, dirs_exist_ok=True)
    inventory = {str(p.relative_to(OUT)): hashlib.sha256(p.read_bytes()).hexdigest()
                 for base in (receipts, capture) for p in base.iterdir() if p.is_file()}
    summary = dict(trials=measurements, scientific_tolerance=0,
                   runtime_stage='ALGO03 recovery only', production_modified=False,
                   receipts_sha256=inventory)
    (OUT/'measurements.json').write_text(json.dumps(summary, indent=2)+'\n')
    runtime = ROOT/'algo03-hierarchical-prototype'
    bound = json.loads((runtime/'runtime-manifest.json').read_text())
    names = bound['experimental_files']
    implementation = dict(
        files_sha256={name: bound['files_sha256'][name] for name in names},
        baseline_files_sha256={name: hashlib.sha256(
            (Path(bound['original_release'])/name).read_bytes()).hexdigest() for name in names},
        runtime_manifest_sha256=hashlib.sha256((runtime/'runtime-manifest.json').read_bytes()
                                              ).hexdigest(),
        source_root=str(runtime), production_deployed=False, tolerance=0,
        prior_observations_solver_budgets_unchanged=True)
    (OUT/'implementation.json').write_text(json.dumps(implementation, indent=2)+'\n')
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.7), constrained_layout=True)
    names = ['Original\nfirst run', 'Earlier runtime\nchanges',
             'New exact\nhierarchical', 'Original\nrepeat']
    values = [r['timing']['wall_seconds'] for r in measurements]
    colors = ['#7d8792', '#5c89bb', '#259b78', '#7d8792']
    bars = axes[0].bar(names, values, color=colors)
    axes[0].bar_label(bars, fmt='%.1f s', padding=3)
    axes[0].set(ylabel='Wall seconds', title='Complete ALGO03 private replay')
    axes[0].set_ylim(0, max(values)*1.17)
    selected = ['target-0-annotation', 'target-0-inclusion', 'target-0-retry']
    labels = ['Annotation', 'Inclusion', 'Matched numerical retry']
    for i, trial in enumerate((measurements[3], measurements[2])):
        xx = [k+(i-.5)*.36 for k in range(len(selected))]
        axes[1].bar(xx, [trial['stages'][k] for k in selected], width=.36,
                    color=['#7d8792', '#259b78'][i], label=['Original repeat', 'Candidate'][i])
    axes[1].set(xticks=range(3), xticklabels=labels, ylabel='Wall seconds',
                title='Same scientific work and solver budgets')
    axes[1].legend()
    for ax in axes:
        ax.grid(axis='y', alpha=.18)
        ax.set_axisbelow(True)
    fig.suptitle('One frozen scan; both c arms exact. Not end-to-end ALGO07 timing.')
    fig.savefig(OUT/'algo03_runtime.png', dpi=155)
    plt.close(fig)
    print(json.dumps(dict(trials={r['name']: r['timing']['wall_seconds'] for r in measurements},
                          files=len(inventory))))


if __name__ == '__main__':
    main()
