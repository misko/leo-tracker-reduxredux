"""Verify full-budget conservative-recovery pairs and render stage coverage."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scalar(value):
    return float.fromhex(value['hex'])


def run(source, output):
    cases, module_sets = [], {}
    for case in ('DS26-0002', 'DS26-0084', 'DS26-0102'):
        files = {side:source/f'{case}-{side}.json' for side in ('reference', 'candidate')}
        if files['reference'].read_bytes() != files['candidate'].read_bytes():
            raise ValueError(f'Scientific outputs differ: {case}')
        receipts = {}
        for side, path in files.items():
            receipt_path = path.with_suffix('.receipt.json')
            r = json.loads(receipt_path.read_text())
            if r['output_sha256'] != sha(path):
                raise ValueError('Output binding differs')
            if not r['conservative'] or (r['rounds'], r['iterations']) != (5, 48):
                raise ValueError('Full-budget conservative comparison required')
            if (r['seed_budget'], r['branch_budget']) != (4, 3):
                raise ValueError('Initial discovery/branch budgets changed')
            for name, digest in r['inputs'].items():
                if sha(Path(r['source'])/name) != digest:
                    raise ValueError('Input binding differs')
            for name, digest in r['additional_inputs'].items():
                if sha(Path(name)) != digest:
                    raise ValueError('Prior/observations binding differs')
            for binding in r['modules'].values():
                if sha(Path(binding['path'])) != binding['sha256']:
                    raise ValueError(f"Numerical module changed: {binding['path']}")
            key = hashlib.sha256(json.dumps(r['modules'], sort_keys=True).encode()).hexdigest()
            module_sets[key] = r['modules']
            receipts[side] = dict(path=str(receipt_path), sha256=sha(receipt_path),
                source=r['source'], inputs=r['inputs'], additional_inputs=r['additional_inputs'],
                modules_sha256=key, tool_sources=r['tool_sources'], seconds=r['seconds'])
        result = json.loads(files['candidate'].read_text())
        initial, recovered = result['initial'], result['recovery']
        winner = initial['choices'][initial['selected_hypothesis']]
        if recovered['status'] != 'complete':
            raise ValueError(f'Unexpected recovery state: {case}')
        summaries = {}
        for arm in ('c0', 'fitted_c'):
            a = winner['arms'][arm]['all_graph_associations']
            b = recovered['arms'][arm]
            summaries[arm] = dict(initial_points=a['accepted_points'],
                initial_tracks=a['accepted_tracks'],
                final_points=b['association']['associated_original_winners'],
                final_tracks=b['association']['associated_tracks'],
                winning_points=b['association']['original_winning_GLRT_points'],
                final_percent=scalar(b['association']['associated_original_percent']),
                calibration_points=b['record']['active_points'],
                calibration_rms_hz=scalar(b['record']['frequency_rms_hz']),
                score=scalar(b['record']['score']))
        cases.append(dict(case=case, exact=True, fingerprint_sha256=sha(files['candidate']),
            receipts=receipts, arms=summaries,
            selected_initial_branch=initial['selected_hypothesis'],
            initial_failed_components=recovered['initial_failed_components'],
            exclusion_history=recovered['exclusion_history'],
            post_salvage_history=recovered['post_salvage_history'],
            salvage=[dict(component=r['component'], candidate_count=r['candidate_count'],
                          supports_tested=r['supports_tested'],
                          proposed_points=r['selected']['points'] if r['selected'] else 0)
                     for r in recovered['trims']]))
    result = dict(scope='Initial search through conservative rejection/refit/salvage',
        full_pipeline_parity=False, qualified_speedup=None, cases=cases,
        module_bindings=module_sets)
    (output/'comparison.json').write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    labels, before, after, counts = [], [], [], []
    for row in cases:
        for arm, data in row['arms'].items():
            labels.append(row['case'].removeprefix('DS26-')+'\n'+arm)
            before.append(100*data['initial_points']/data['winning_points'])
            after.append(data['final_percent'])
            counts.append(data['final_points'])
    x = np.arange(len(labels))
    axes[0].bar(x-.18, before, .36, color='#56B4E9', label='Initial search')
    axes[0].bar(x+.18, after, .36, color='#0072B2', label='After conservative recovery')
    for k, (percent, count) in enumerate(zip(after, counts, strict=True)):
        axes[0].text(k+.18, percent+1, str(count), ha='center', fontsize=8)
    axes[0].set(xticks=x, xticklabels=labels, ylim=(0, 100),
                ylabel='Associated winning GLRT points (%)',
                title='All-track association after frozen extension')
    for k, row in enumerate(cases):
        proposed = sum(r['proposed_points'] for r in row['salvage'])
        final = row['arms']['c0']['calibration_points']
        base = row['exclusion_history'][-1]['active_points']
        start = base+proposed
        axes[1].bar(k, base, color='#999999', label='Before salvage' if k == 0 else None)
        axes[1].bar(k, final-base, bottom=base, color='#009E73',
                    label='Net retained calibration gain' if k == 0 else None)
        axes[1].bar(k, start-final, bottom=final, color='#D55E00',
                    label='Points removed by paired refit' if k == 0 else None)
        axes[1].text(k, start+25, f'{final} retained', ha='center', fontsize=9)
    axes[1].set(xticks=range(len(cases)),
                xticklabels=[r['case'].removeprefix('DS26-') for r in cases],
                ylabel='Curved calibration points',
                title='Recovered curves still face both-arm gates')
    axes[1].set_ylim(0, axes[1].get_ylim()[1]*1.2)
    for ax in axes:
        ax.grid(axis='y', alpha=.2)
        ax.legend(loc='upper left', fontsize=7)
    fig.suptitle('ALGO07v3 · exact match to reference through conservative recovery\n'
                 'Production fitting budgets; later family recovery and publication excluded')
    fig.tight_layout()
    fig.savefig(output/'conservative-parity.png', dpi=160)
    plt.close(fig)
    print(json.dumps([dict(case=r['case'], exact=r['exact'], arms=r['arms'],
                          salvage=r['salvage'], post_salvage=r['post_salvage_history'])
                      for r in cases], indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)
