"""Validate exact initial-search pairs and render their scientific summaries."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scalar(value):
    return float.fromhex(value['hex'])


def run(source, output):
    comparisons, module_sets = [], {}
    for case, budget in [('DS26-0002', 'bounded'), ('DS26-0084', 'bounded'),
                         ('DS26-0102', 'bounded'), ('DS26-0084', 'full')]:
        paths = {side:source/f'{case}-{side}-{budget}.json'
                 for side in ('reference', 'candidate')}
        values = {side:json.loads(path.read_text()) for side, path in paths.items()}
        if paths['reference'].read_bytes() != paths['candidate'].read_bytes():
            raise ValueError(f'Initial search differs: {case} {budget}')
        receipts = {}
        for side, path in paths.items():
            receipt_path = path.with_suffix('.receipt.json')
            receipt = json.loads(receipt_path.read_text())
            if receipt['output_sha256'] != sha(path):
                raise ValueError('Result binding changed')
            for name, digest in receipt['inputs'].items():
                if sha(Path(receipt['source'])/name) != digest:
                    raise ValueError('Input binding changed')
            for binding in receipt['modules'].values():
                if sha(Path(binding['path'])) != binding['sha256']:
                    raise ValueError(f"Module binding changed: {binding['path']}")
            module_key = hashlib.sha256(json.dumps(
                receipt['modules'], sort_keys=True).encode()).hexdigest()
            module_sets[module_key] = receipt['modules']
            receipts[side] = dict(path=str(receipt_path), sha256=sha(receipt_path),
                source=receipt['source'], inputs=receipt['inputs'],
                modules_sha256=module_key, seconds=receipt['seconds'])
            expected = (5, 48) if budget == 'full' else (1, 4)
            if (receipt['rounds'], receipt['iterations']) != expected:
                raise ValueError('Unexpected search budget')
            if receipt['seed_budget'] != 4 or receipt['branch_budget'] != 3:
                raise ValueError('Discovery/branch budget changed')
        item = values['candidate']
        winner = item['choices'][item['selected_hypothesis']]
        comparisons.append(dict(case=case, budget=budget, exact=True,
            fingerprint_sha256=sha(paths['candidate']), receipts=receipts,
            unique_hypotheses=item['unique_RF_hypotheses'],
            fully_fitted_hypotheses=item['fully_fitted_hypotheses'],
            selected_hypothesis=item['selected_hypothesis'],
            selected={arm:dict(score=scalar(value['fit']['score']),
                accepted_curved_points=value['metrics']['accepted_points'],
                accepted_points=value['all_graph_associations']['accepted_points'],
                accepted_tracks=value['all_graph_associations']['accepted_tracks'])
                for arm, value in winner['arms'].items()}))
    document = dict(scope='Initial regional search only; excludes later recovery and publication',
        full_pipeline_parity=False, qualified_speedup=None,
        comparisons=comparisons, module_bindings=module_sets)
    (output/'comparison.json').write_text(json.dumps(document, indent=2, sort_keys=True)+'\n')
    full = json.loads((source/'DS26-0084-candidate-full.json').read_text())
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    colors = ['#0072B2', '#D55E00', '#009E73']
    summaries = []
    for choice, color in zip(full['choices'], colors, strict=True):
        for arm, linestyle in [('c0', '-'), ('fitted_c', '--')]:
            data = choice['arms'][arm]
            scores = [scalar(r['fit']['score']) for r in data['phase_rounds']]
            axes[0].plot(range(1, len(scores)+1), scores, marker='o', markersize=3,
                         color=color, linestyle=linestyle,
                         label=f"Branch {choice['hypothesis']} · {arm}")
            summaries.append(dict(branch=choice['hypothesis'], arm=arm, scores=scores,
                accepted_curved_points=data['metrics']['accepted_points'],
                extended_points=data['all_graph_associations']['added_points'],
                accepted_points=data['all_graph_associations']['accepted_points'],
                accepted_tracks=data['all_graph_associations']['accepted_tracks']))
    for k, data in enumerate(summaries):
        axes[1].bar(k, data['accepted_curved_points'], color='#0072B2',
                    label='Accepted curved calibration points' if k == 0 else None)
        axes[1].bar(k, data['extended_points'], bottom=data['accepted_curved_points'],
                    color='#56B4E9',
                    label='Frozen-calibration extension points' if k == 0 else None)
        axes[1].text(k, data['accepted_points']+20, str(data['accepted_points']),
                     ha='center', va='bottom', fontsize=8)
    axes[0].set(xlabel='Phase-refresh round', ylabel='Full frequency/prior score (lower is better)',
                xticks=[1, 2, 3, 4, 5], title='Production-budget phase refresh')
    axes[1].set(xticks=range(len(summaries)),
                xticklabels=[f"B{d['branch']}\n{d['arm']}" for d in summaries],
                ylabel='Associated native GLRT points',
                title='Profile, conditional and owner gates')
    axes[1].set_ylim(0, max(d['accepted_points'] for d in summaries)*1.25)
    for ax in axes:
        ax.grid(alpha=.2, axis='y')
        ax.legend(fontsize=7, loc='best')
    fig.suptitle('DS26-0084 · standalone initial search exactly matches reference\n'
                 f"Selected branch {full['selected_hypothesis']} for both c arms; "
                 'later recovery excluded')
    fig.tight_layout()
    fig.savefig(output/'initial-search-parity.png', dpi=160)
    plt.close(fig)
    (output/'branch-summary.json').write_text(json.dumps(summaries, indent=2)+'\n')
    print(json.dumps([dict(case=r['case'], budget=r['budget'], exact=r['exact'],
                          selected=r['selected']) for r in comparisons], indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)
