"""Verify complete cavity policy comparisons and render paired selection evidence."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from compare_algo07v3_cavity import compare

matplotlib.use('Agg')
import matplotlib.pyplot as plt


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(source, output):
    cases, modules = [], {}
    for case in ('DS26-0002', 'DS26-0084', 'DS26-0102'):
        paths = {s: source/f'{case}-{s}.json' for s in ('reference', 'candidate')}
        if paths['reference'].read_bytes() != paths['candidate'].read_bytes():
            raise ValueError(f'Fresh scientific outputs differ: {case}')
        receipts = {}
        for side, path in paths.items():
            receipt_path = path.with_suffix('.receipt.json')
            r = json.loads(receipt_path.read_text())
            if r['output_sha256'] != sha(path):
                raise ValueError('Output binding differs')
            if not r['cavity_policy'] or (r['rounds'], r['iterations']) != (5, 48):
                raise ValueError('Full-budget cavity comparison required')
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
                    raise ValueError(f"Numerical source changed: {binding['path']}")
            for name, digest in r['tool_sources'].items():
                if sha(Path(name)) != digest:
                    raise ValueError(f'Tool source changed: {name}')
            key = hashlib.sha256(json.dumps(r['modules'], sort_keys=True).encode()).hexdigest()
            modules[key] = r['modules']
            receipts[side] = dict(path=str(receipt_path), sha256=sha(receipt_path),
                source=r['source'], inputs=r['inputs'], additional_inputs=r['additional_inputs'],
                module_set=key, tool_sources=r['tool_sources'], seconds=r['seconds'])
        audit_path = source/f'{case}-persisted.json'
        audit = json.loads(audit_path.read_text())
        documents = {}
        for key, item in audit['inputs'].items():
            path = Path(item['path'])
            if sha(path) != item['sha256']:
                raise ValueError('Archived comparison binding differs')
            documents[key] = json.loads(path.read_text())
        compare(documents['nominations'], documents['position'], documents['candidate'])
        p, n = documents['position'], documents['nominations']
        baseline = p['baseline_corrected_loss']
        trials = [dict(replacements=t['replacements'], paired_valid=t['paired_valid'],
            constrained=t['constrained_refinement_attempted'],
            gains={a:baseline[a]-r['corrected_selection_loss'] for a,r in t['arms'].items()})
            for t in p['trials']]
        arms = {a:{k:r[k] for k in ('endpoint_east_north_km', 'RMS_hz', 'active_points')}
                for a,r in p['policy_arms'].items()}
        cases.append(dict(case=case, fresh_exact=True, persisted_exact=True,
            output_sha256=sha(paths['candidate']), receipts=receipts,
            persisted_receipt=dict(path=str(audit_path), sha256=sha(audit_path), **audit),
            families=len(n['families']), trials=trials, adopted=p['accepted'],
            selected=p['selected']['replacements'] if p['accepted'] else [], arms=arms,
            legacy_reference_repairs=p['legacy_fit_reference_replay'],
            sticky_control_accepted=p['sticky_control_accepted'],
            sticky_penalty=p['search_penalty'], baseline_corrected_loss=baseline))
    document = dict(scope='Initial search through complete family-cavity selection',
        full_pipeline_parity=False, qualified_speedup=None, module_bindings=modules, cases=cases)
    (output/'comparison.json').write_text(json.dumps(document, indent=2, sort_keys=True)+'\n')
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.8))
    for ax, row in zip(axes, cases, strict=True):
        if not row['trials']:
            ax.text(.5, .5, 'No positive replacement offer\nOriginal assignment retained',
                    ha='center', va='center', transform=ax.transAxes)
            ax.set_xticks([])
        else:
            x = np.arange(len(row['trials']))
            labels = []
            for trial in row['trials']:
                identities = ', '.join(str(r['norad']) for r in trial['replacements'])
                status = 'paired valid' if trial['paired_valid'] else 'rejected'
                if row['adopted'] and trial['replacements'] == row['selected']:
                    status = 'selected'
                labels.append(identities+'\n'+status)
            for offset, arm, color in ((-.18, 'c0', '#0072B2'), (.18, 'fitted_c', '#009E73')):
                values = [t['gains'][arm] for t in row['trials']]
                ax.bar(x+offset, values, .36, color=color, label=arm)
            ax.set(xticks=x, xticklabels=labels)
            ax.legend(fontsize=8)
        ax.axhline(0, color='black', lw=1)
        ax.axhline(row['sticky_penalty'], color='#D55E00', ls=':',
                   label='Historical sticky penalty')
        ax.set(title=row['case']+' · '+('replacement adopted' if row['adopted'] else 'retained'),
               ylabel='Corrected selection-loss improvement')
        ax.grid(axis='y', alpha=.2)
    fig.suptitle('ALGO07v3 · exact complete-family cavity policy parity\n'
        'Adopt valid pair with positive c=0 gain; dotted line is the historical control penalty')
    fig.tight_layout()
    fig.savefig(output/'cavity-parity.png', dpi=160)
    plt.close(fig)
    print(json.dumps([{k:v for k,v in r.items() if k not in ('receipts', 'persisted_receipt')}
                      for r in cases], indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)
