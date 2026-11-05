"""Check exact signed-context evidence and render qualification/adoption results."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from compare_algo07v3_signed import compare

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def scalar(value):
    return float.fromhex(value['hex'])


def run(reference, candidate, output):
    cases, modules = [], {}
    for case in ('DS26-0002', 'DS26-0084', 'DS26-0102'):
        paths = dict(reference=reference/f'{case}-reference.json',
                     candidate=candidate/f'{case}-candidate.json')
        if paths['reference'].read_bytes() != paths['candidate'].read_bytes():
            raise ValueError(f'Fresh scientific outputs differ: {case}')
        receipts = {}
        for side, path in paths.items():
            receipt_path = path.with_suffix('.receipt.json')
            r = json.loads(receipt_path.read_text())
            if r['output_sha256'] != sha(path):
                raise ValueError('Output binding differs')
            if not r['signed_policy'] or (r['rounds'], r['iterations']) != (5, 48):
                raise ValueError('Full-budget signed-policy comparison required')
            if (r['seed_budget'], r['branch_budget']) != (4, 3):
                raise ValueError('Initial discovery/branch budgets changed')
            for name, digest in r['inputs'].items():
                if sha(Path(r['source'])/name) != digest:
                    raise ValueError('Input binding differs')
            for name, digest in r['additional_inputs'].items():
                if sha(Path(name)) != digest:
                    raise ValueError('Additional input binding differs')
            for binding in r['modules'].values():
                if sha(Path(binding['path'])) != binding['sha256']:
                    raise ValueError(f"Numerical module changed: {binding['path']}")
            source_bindings = {}
            for name, digest in r['tool_sources'].items():
                source = Path(name)
                if sha(source) != digest:
                    saved = {'check_algo07v3_position.py': 'reference-checker.py.txt',
                             'algo07v3_signed_oracle.py': 'reference-oracle.py.txt'}
                    source = Path(__file__).parent/saved[source.name]
                if sha(source) != digest:
                    raise ValueError(f'Tool source changed: {name}')
                source_bindings[name] = dict(verified_source=str(source), sha256=digest)
            key = hashlib.sha256(json.dumps(r['modules'], sort_keys=True).encode()).hexdigest()
            modules[key] = r['modules']
            receipts[side] = dict(path=str(receipt_path), sha256=sha(receipt_path),
                source=r['source'], inputs=r['inputs'], additional_inputs=r['additional_inputs'],
                module_set=key, tool_sources=source_bindings, seconds=r['seconds'])
        audit_path = candidate/f'{case}-persisted.json'
        audit = json.loads(audit_path.read_text())
        archive_path = Path(audit['archived_path'])
        if sha(archive_path) != audit['archived_sha256']:
            raise ValueError('Archived output binding differs')
        if sha(paths['candidate']) != audit['candidate_sha256']:
            raise ValueError('Persisted comparison candidate binding differs')
        result = json.loads(paths['candidate'].read_text())
        archived = json.loads(archive_path.read_text())
        compare(archived, result)
        context = result['signed_policy']
        selection = context['signed']['selection']
        summary = {k:v for k,v in selection.items() if k not in ('prefix', 'all_past')}
        for key in ('coefficient', 'future_gain', 'disjoint_future_gain'):
            summary[key] = scalar(summary[key])
        arms = {a:{k:r[k] for k in ('endpoint_east_north_km', 'RMS_hz',
                    'negative_twice_elbo', 'active_points')}
                for a,r in archived['baseline_arms'].items()}
        cases.append(dict(case=case, fresh_exact=True, persisted_exact=True,
            output_sha256=sha(paths['candidate']), receipts=receipts,
            persisted_receipt=dict(path=str(audit_path), sha256=sha(audit_path), **audit),
            selection=summary, signed_adopted=context['signed']['accepted'], arms=arms,
            linear_points=sum(e['points'] for e in context['entries'])))
    document = dict(scope='Initial search through signed causal-prior context',
        full_pipeline_parity=False, qualified_speedup=None, module_bindings=modules, cases=cases)
    (output/'comparison.json').write_text(json.dumps(document, indent=2, sort_keys=True)+'\n')
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    x = np.arange(len(cases))
    for offset, name, count, color in (
        (-.18, 'future_gain', 'future_count', '#0072B2'),
        (.18, 'disjoint_future_gain', 'disjoint_future_count', '#009E73')):
        gain = [r['selection'][name] for r in cases]
        threshold = [np.log(r['selection'][count])+2*np.log(4) for r in cases]
        axes[0].bar(x+offset, gain, .36, color=color, label=name.replace('_', ' '))
        axes[0].scatter(x+offset, threshold, marker='_', s=250, c='black')
    axes[0].axhline(0, color='gray', lw=.6)
    axes[0].set(ylabel='Historical predictive score improvement',
                title='Both historical gates must pass\nBlack marks: required complexity penalty',
                xticks=x, xticklabels=[r['case'].removeprefix('DS26-') for r in cases])
    axes[0].legend(fontsize=8)
    for i, row in enumerate(cases):
        for offset, arm, color in ((-.18, 'c0', '#56B4E9'), (.18, 'fitted_c', '#CC79A7')):
            value = row['arms'][arm]['RMS_hz']
            axes[1].bar(i+offset, value, .36, color=color, label=arm if i == 0 else None)
            axes[1].text(i+offset, value+1, f'{value:.2f}', ha='center', fontsize=8)
    axes[1].set(ylabel='Curved frequency RMS (Hz)', ylim=(0, 90),
                title='Selected incumbent · exact reference/v3 parity',
                xticks=x, xticklabels=[r['case'].removeprefix('DS26-')+'\n'+
                    ('signed adopted' if r['signed_adopted'] else 'ordinary retained')
                    for r in cases])
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.grid(axis='y', alpha=.2)
    fig.suptitle('ALGO07v3 · signed phase-prior qualification and paired fitting\n'
                 'All history precedes RF; frequency fit is not position accuracy')
    fig.tight_layout()
    fig.savefig(output/'signed-parity.png', dpi=160)
    plt.close(fig)
    print(json.dumps([{k:v for k,v in r.items() if k not in ('receipts', 'persisted_receipt')}
                      for r in cases], indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.reference, args.candidate, args.output)
