"""Validate full-budget history-policy evidence and render matched-arm results."""
import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
import numpy as np
from compare_algo07v3_history import compare

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
            if not r['history_policy'] or (r['rounds'], r['iterations']) != (5, 48):
                raise ValueError('Full-budget history-policy comparison required')
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
        archive_path = Path(audit['archived_path'])
        if sha(archive_path) != audit['archived_sha256']:
            raise ValueError('Archived production output binding differs')
        if sha(paths['candidate']) != audit['candidate_sha256']:
            raise ValueError('Persisted comparison candidate binding differs')
        result = json.loads(paths['candidate'].read_text())
        archived = json.loads(archive_path.read_text())
        compare(archived, result)
        h = result['history_policy']
        arms = {}
        for arm, a in archived['policy_arms'].items():
            arms[arm] = {k:a[k] for k in ('active_points', 'RMS_hz',
                'endpoint_east_north_km', 'negative_twice_elbo')}
            arms[arm]['used_linear_points'] = h['linear_used_points']
        cases.append(dict(case=case, fresh_exact=True, persisted_exact=True,
            fingerprint_sha256=sha(paths['candidate']), receipts=receipts,
            persisted_receipt=dict(path=str(audit_path), sha256=sha(audit_path), **audit),
            arms=arms, linear_offered_tracks=h['linear_offered_tracks'],
            linear_offered_points=h['linear_offered_points'],
            linear_used_points=h['linear_used_points'], fallback=h['fallback'],
            history_qualified=h['earlier_TLE_validation_qualified'],
            curved_gate_history=h['curved_gate_history']))
    document = dict(scope='Initial search through family/history predictive-linear policy',
        full_pipeline_parity=False, qualified_speedup=None, module_bindings=modules, cases=cases)
    (output/'comparison.json').write_text(json.dumps(document, indent=2, sort_keys=True)+'\n')
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8))
    labels, curved, used, unused, rms = [], [], [], [], []
    for row in cases:
        for arm, data in row['arms'].items():
            labels.append(row['case'].removeprefix('DS26-')+'\n'+arm)
            curved.append(data['active_points'])
            used.append(row['linear_used_points'])
            unused.append(row['linear_offered_points']-row['linear_used_points'])
            rms.append(data['RMS_hz'])
    x = np.arange(len(labels))
    axes[0].bar(x, curved, color='#0072B2', label='Retained curved calibration')
    axes[0].bar(x, used, bottom=curved, color='#009E73', label='Used predictive linear points')
    axes[0].bar(x, unused, bottom=np.array(curved)+used, color='#E69F00',
                label='Offered linear points; paired fallback')
    for i, (c, n) in enumerate(zip(curved, used, strict=True)):
        axes[0].text(i, c+n+12, str(c+n), ha='center', fontsize=8)
    axes[0].set(ylabel='Points in this fitting policy', ylim=(0, 5000),
                title='Same retained evidence and paired fallback')
    axes[0].legend(fontsize=7, loc='upper left')
    axes[1].bar(x, rms, color=['#56B4E9', '#CC79A7']*3)
    for i, value in enumerate(rms):
        axes[1].text(i, value+.5, f'{value:.2f}', ha='center', fontsize=8)
    axes[1].set(ylabel='Curved frequency RMS (Hz)', ylim=(0, max(rms)*1.18),
                title='Frequency fit, not localization accuracy')
    for ax in axes:
        ax.set(xticks=x, xticklabels=labels)
        ax.grid(axis='y', alpha=.2)
    fig.suptitle('ALGO07v3 · exact family/history policy parity on three scans\n'
                 'Both arms match fresh oracle and archived production; later recovery excluded')
    fig.tight_layout()
    fig.savefig(output/'history-parity.png', dpi=160)
    plt.close(fig)
    print(json.dumps([{k:v for k,v in r.items() if k not in ('receipts', 'persisted_receipt')}
                      for r in cases], indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.source, args.output)
