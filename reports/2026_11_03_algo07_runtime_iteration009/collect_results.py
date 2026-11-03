"""Bind ALGO03 qualification to the original, predeclared numerical contract."""

import json
import shutil
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
PREVIOUS = ROOT/'reports/2026_11_03_algo07_runtime_iteration008'
RUN = Path('/srv/bulk/leo/research/algo07-runtime-20261103')


def read(path):
    return json.loads(path.read_text())


def copy(path, name):
    target = OUT/'receipts'/name
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(path, target)
    return str(target.relative_to(ROOT))


def main():
    rows = []
    for case in ('single', 'joint'):
        prefix = f'algo03-{case}'
        root = RUN/('algo03-fresh' if case == 'single' else 'algo03-joint')
        source = (PREVIOUS/'receipts'/f'{prefix}-parity.json' if case == 'single'
                  else root/'cache-fixed-predeclared-contract.json')
        parity = read(source)
        assert parity['passed'] and not parity['differences']
        row = dict(case=case, parity_path=copy(source, f'{prefix}-parity.json'), timing_paths=[])
        for label in ('baseline-repeat' if case == 'single' else 'baseline', 'cache-fixed'):
            value = read(root/label/'timing.json')
            assert value['successful_execution'] and value['reference_after']['verified']
            row['timing_paths'].append(copy(root/label/'timing.json',
                                           f'{prefix}-{label}-timing.json'))
        if case == 'joint':
            row['strict_parity_path'] = copy(root/'cache-fixed-parity-v2.json',
                                             'joint-strict-parity.json')
            row['kernel_protocol_path'] = copy(
                ROOT/'reports/2026_11_03_algo07_runtime_iteration002/protocol.json',
                'predeclared-kernel-protocol.json')
        rows.append(row)
    final_rows = read(PREVIOUS/'qualification.json')['algo07_cases']
    for row in final_rows:
        assert read(ROOT/row['parity_path'])['passed']
    for name in ('candidate-runtime-manifest.json', 'population-parity.json',
                 'saved-policy-parity.json'):
        copy(PREVIOUS/'receipts'/name, name)
    shutil.copyfile(PREVIOUS/'cache-fix.json', OUT/'cache-fix.json')
    original_population = RUN/'population/original-contractions-reference-parity.json'
    assert read(original_population)['passed']
    copy(original_population, 'original-order-population-parity.json')
    copy(RUN/'population/original-contractions-parity.json', 'cross-kernel-strict-comparison.json')
    for case in ('algo03-fresh', 'algo03-joint'):
        parity = read(RUN/case/'original-contractions-parity.json')
        assert parity['passed']
        copy(RUN/case/'original-contractions-parity.json', case+'-original-order-parity.json')
        copy(RUN/case/'original-contractions/timing.json', case+'-original-order-timing.json')
    qualification = dict(passed=True, exact_decisions_and_objectives=True,
                         diagnostic_tolerance='original iteration002 kernel protocol only',
                         algo03_cases=rows, algo07_cases=final_rows, production_deployed=False)
    (OUT/'qualification.json').write_text(json.dumps(qualification, indent=2)+'\n')
    summary = []
    for case, folder, baseline in [('single', 'algo03-fresh', 'baseline-repeat'),
                                   ('joint', 'algo03-joint', 'baseline')]:
        root = RUN/folder
        times = [read(root/label/'timing.json')['wall_seconds'] for label in
                 (baseline, 'original-contractions', 'cache-fixed')]
        summary.append(dict(case=case, baseline_seconds=times[0], original_order_seconds=times[1],
                            candidate_seconds=times[2], candidate_speedup=times[0]/times[2]))
    (OUT/'measurements.json').write_text(json.dumps(summary, indent=2)+'\n')
    fig, ax = plt.subplots(figsize=(9, 5))
    for j, (key, label, color) in enumerate([
        ('baseline_seconds', 'Original production', '#66788a'),
        ('original_order_seconds', 'Optimized, original contraction order', '#e3b34c'),
        ('candidate_seconds', 'Full candidate, predeclared bounds', '#18877f'),
    ]):
        ax.bar([i+(j-1)*.25 for i in range(2)], [r[key] for r in summary],
               width=.25, label=label, color=color)
    ax.set_xticks(range(2), ['Single-family case', 'Joint-family case'])
    ax.set_ylabel('Complete ALGO03 stage seconds')
    ax.set_title('Exact positions, owners, objectives and decisions in both calibration arms')
    ax.legend(fontsize=9)
    fig.tight_layout()
    fig.savefig(OUT/'runtime.png', dpi=150)
    plt.close(fig)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
