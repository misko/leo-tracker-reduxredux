"""Render full worker timings without double-counting nested recovery stages."""

import hashlib
import json
from pathlib import Path

import matplotlib

matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

OUT = Path(__file__).resolve().parent
DEV = Path('/srv/bulk/leo-dev')


def read(path):
    return json.loads(path.read_bytes())


def main():
    profile = OUT.parent / '2026_11_06_algo07v3_full_profile'
    bindings = read(profile / 'profile/plan.json')['bindings']
    changed = [p for p, sha in bindings.items()
               if hashlib.sha256(Path(p).read_bytes()).hexdigest() != sha]
    if changed:
        raise ValueError(f'Full-profile bindings changed: {changed}')
    cases = {}
    for label in ('0002', '0066', '0084', '0170', '0102'):
        if label in ('0002', '0066'):
            root = DEV / f'algo07v3-control-view-native-{label}-20261106/candidate/attempt'
            clock = read(root / 'supervisor.json')
            scope = 'unprofiled native standalone'
        elif label == '0102':
            root = DEV / 'algo07v3-joint-control-census-0102-20261106'
            observed = read(root / 'result.json')
            clock = dict(observed['process'], worker=observed['worker'])
            scope = 'full standalone with joint-control fingerprint observer'
        else:
            root = DEV / f'algo07v3-fit-census-subset-r2-20261106/DS26-{label}-run/attempt'
            clock = read(root / 'supervisor.json')
            scope = 'unprofiled native standalone'
        assert clock['returncode'] == 0 and clock['worker']['status'] == 'complete'
        raw = [json.loads(s) for s in (root / 'worker.log').read_text().splitlines()
               if s.startswith('{')]
        stages = {r['stage']: r['seconds'] for r in raw if r.get('event') == 'stage'}
        worker = clock['worker']
        stages.update(evidence_save=worker['evidence_save_seconds'],
                      publication=worker['publication_seconds'])
        stages['other_process'] = clock['process_seconds'] - sum(stages.values())
        assert stages['other_process'] >= 0
        receipt = worker['scientific_receipt']['receipt']
        cases[label] = dict(seconds=clock['process_seconds'], stages=stages, scope=scope,
                            receipt=receipt, receipt_sha=worker['scientific_receipt']['sha256'],
                            source_clock=str(root),
                            recovery_stage_names=[r['stage'] for r in raw
                                                  if r.get('event') == 'recovery_stage'])
        (OUT / f'{label}-clock.json').write_text(json.dumps(clock, indent=2) + '\n')
    summary = dict(cases=cases, full_profile_bindings_verified=len(bindings),
                   runtime_modified=False, production_modified=False,
                   new_speedup_measured=False)
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    keys = sorted({k for c in cases.values() for k in c['stages']},
                  key=lambda k: sum(c['stages'].get(k, 0) for c in cases.values()), reverse=True)
    table = '| Stage (seconds) | ' + ' | '.join('DS26-' + x for x in cases) + ' |\n'
    table += '| --- | ' + ' | '.join('---:' for _ in cases) + ' |\n'
    for k in keys:
        table += '| ' + k + ' | ' + ' | '.join(
            f"{c['stages'].get(k, 0):.3f}" for c in cases.values()) + ' |\n'
    table += '| **Complete process** | ' + ' | '.join(
        f"**{c['seconds']:.3f}**" for c in cases.values()) + ' |\n'
    (OUT / 'stages.md').write_text(table)
    groups = {
        'Initial search': ['initial'], 'Predictive recovery': ['predictive'],
        'Numerical recovery': ['numerical'],
        'Other calibration / fitting': ['conservative', 'family', 'signed', 'cavity',
                                         'addition'],
        'Reassociation': ['incumbent', 'ranking', 'admission', 'final'],
        'Figure data + PNGs': ['plot_evidence', 'png_rendering'],
        'Save + publication': ['evidence_save', 'publication'],
    }
    fig, ax = plt.subplots(figsize=(12, 5.5), layout='constrained')
    y, left = np.arange(len(cases)), np.zeros(len(cases))
    for name, stages in groups.items():
        widths = np.array([sum(c['stages'].get(k, 0) for k in stages) for c in cases.values()])
        ax.barh(y, widths, left=left, label=name)
        left += widths
    totals = np.array([c['seconds'] for c in cases.values()])
    ax.barh(y, totals - left, left=left, label='Preparation, screening + other', color='#aaaaaa')
    for i, total in enumerate(totals):
        ax.text(total + 4, i, f'{total:.1f} s', va='center')
    ax.set(yticks=y, yticklabels=['DS26-' + k + (' *' if k == '0102' else '') for k in cases],
           xlabel='Elapsed seconds, native GLRT input ready through all artifacts published',
           xlim=(0, max(totals) * 1.15),
           title='ALGO07v3: stage costs depend on the scan\n'
                 'Three CPU slots; * joint-control observer; these are not speed comparisons')
    ax.legend(loc='upper center', bbox_to_anchor=(.5, -.16), ncol=3)
    fig.savefig(OUT / 'scan-stages.png', dpi=150)
    plt.close(fig)


if __name__ == '__main__':
    main()
