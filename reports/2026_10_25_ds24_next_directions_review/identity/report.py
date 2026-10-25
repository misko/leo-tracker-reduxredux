"""Summarize sealed identity diagnostics; no propagation or model evaluation."""
import hashlib
import json
import math
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent


def read(path):
    return json.loads(Path(path).read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(name, value):
    path = HERE / name
    if path.exists():
        raise FileExistsError(path)
    path.write_text(json.dumps(value, indent=2) + '\n')


def main():
    inv = read(HERE / 'inventory.json')
    first = read(HERE / 'results.json')
    owner = read(HERE / 'owner02_results.json')
    checks = []
    for seal_name in ('seal.json', 'owner02_seal.json'):
        for name, expected in read(HERE / seal_name)['files'].items():
            checks.append(dict(test='sealed file unchanged', file=name,
                               passed=sha(HERE / name) == expected))
    for path, expected in inv['input_source_sha256'].items():
        checks.append(dict(test='inventory input unchanged', file=path,
                           passed=sha(path) == expected))
    ownership = []
    for row in inv['rows']:
        target = row['target']
        ledger = read(target['parent_ledger_path'])
        sources = [dict(component=target['component'], observation_ids=target['observation_ids'])]
        sources += row['other_same_family_raw_sources']
        ids = [oid for source in sources for oid in source['observation_ids']]
        overlaps = {arm: len(set(ids) & set(record['accepted_observation_ids']))
                    for arm, record in ledger['coverage'].items()}
        record = dict(case=row['case'], raw_sources=len(sources), points=len(ids),
                      distinct_ids=len(set(ids)), parent_overlap_by_arm=overlaps,
                      accepted_same_candidate_owners=row['accepted_same_candidate_owners'])
        ownership.append(record)
        checks.append(dict(test='whole-source native ownership', case=row['case'],
                           passed=len(ids) == len(set(ids)) and not any(overlaps.values())))
    checks.extend(owner['tests'])
    checks.append(dict(test='all saved single-source scores qualified',
                       passed=len(first['comparisons']) == 10 and
                       all(row['numerically_qualified'] for row in first['comparisons'])))
    checks.append(dict(test='owner score convergence at saved positions',
                       passed=all(row['maximum_1281_2561_score_difference'] <= 1e-3
                                  for row in owner['owner_challenges'])))
    pair = []
    for arm in ('c0', 'fitted_c'):
        pool = {row['norad']: row for row in first['comparisons']
                if row['case'] == 'DS24-0012' and row['arm'] == arm}
        delta = pool[66259]['objective'] - pool[57743]['objective']
        pair.append(dict(arm=arm, nominal_57743_NLL=pool[57743]['objective'],
                         alternate_66259_NLL=pool[66259]['objective'],
                         alternate_minus_nominal_NLL=delta,
                         conditional_BF_57743_over_66259=math.exp(delta / 2),
                         fixed_archived_alias=1, equal_identity_weights=True,
                         numerically_identical_phase_priors=False,
                         calibrated_identity_probability=False))
    gains = []
    for row in owner['owner_challenges']:
        for item in row['scores']['1281']['owners']:
            gains.append(dict(arm=row['arm'], component=item['component'],
                              points=item['points'], marginal_NLL=item['marginal_NLL'],
                              held_owner_conditional_NLL=item['conditional_NLL'],
                              marginal_minus_conditional=item['marginal_NLL'] - item['conditional_NLL']))
    summary = dict(ownership=ownership, candidate_pair=pair, owner_scores=gains,
                   cumulative_scientific_seconds=owner['cumulative_scientific_seconds'],
                   position_fits=0, GPS_used=False, qualified_identities=0,
                   phase_prior_policy='same construction; original candidate-specific causal parameters',
                   owner_folds_are_independent=False, receiver_diversity='RX1 only')
    write('evidence_summary.json', summary)
    write('checks.json', dict(all_passed=all(row['passed'] for row in checks), checks=checks))

    fig, axes = plt.subplots(1, 2, figsize=(10.7, 4.1))
    colors = ['#3073ad', '#d27828']
    axes[0].barh([1, 0], [row['alternate_minus_nominal_NLL'] for row in pair], color=colors)
    axes[0].axvline(0, color='black', linewidth=.8)
    axes[0].set_yticks([1, 0], ['Saved c = 0 parent', 'Saved fitted-c parent'])
    axes[0].set_xlim(-2.1, 2.1)
    axes[0].set_xlabel('NLL(66259) − NLL(57743)\npositive favors 57743; negative favors 66259')
    axes[0].set_title('0012: weak, state-dependent candidate ranking')
    for y, row in zip([1, 0], pair):
        value = row['alternate_minus_nominal_NLL']
        axes[0].text(value + (.06 if value > 0 else -.06), y, f'{value:+.3f}',
                     ha='left' if value > 0 else 'right', va='center', fontsize=9)
    labels = ['CH2 T005\n53 IDs', 'CH4 T000\n85 IDs', 'CH7 T004\n36 IDs', 'CH8 T004\n15 IDs']
    x = np.arange(4)
    for index, arm in enumerate(('c0', 'fitted_c')):
        values = [row['marginal_minus_conditional'] for row in gains if row['arm'] == arm]
        axes[1].bar(x + (index - .5) * .34, values, .34, color=colors[index],
                    label='Saved c = 0 parent' if index == 0 else 'Saved fitted-c parent')
    axes[1].set_xticks(x, labels)
    axes[1].set_ylabel('Marginal − held-owner conditional NLL')
    axes[1].set_title('0013: conditional consistency under assigned 60108')
    axes[1].legend(fontsize=8, frameon=False)
    fig.text(.5, .01, 'All sources RX1; no identity qualification. Overlapping owner folds must not be summed.\n'
             '0012 uses archive alias 1 and candidate-specific causal priors; saved parent positions and calibration both differ.',
             ha='center', fontsize=8)
    fig.tight_layout(rect=(0, .11, 1, 1))
    fig.savefig(HERE / 'identity_diagnostics.png', dpi=180)
    fig.savefig(HERE / 'identity_diagnostics.pdf')
    plt.close(fig)
    names = ['inventory.json', 'protocol.json', 'results.json', 'seal.json', 'owner02.py',
             'owner02_protocol.json', 'owner02_results.json', 'owner02_seal.json',
             'report.py', 'evidence_summary.json', 'checks.json', 'FINDINGS.md',
             'identity_diagnostics.png', 'identity_diagnostics.pdf']
    write('report_seal.json', dict(files={name: sha(HERE / name) for name in names},
                                 scientific_fits=0, GPS_used=False,
                                 qualified_identities=0, all_checks_passed=all(row['passed'] for row in checks)))
    print(json.dumps(dict(all_checks_passed=all(row['passed'] for row in checks),
                          candidate_pair=pair, owner_scores=gains), indent=2))


if __name__ == '__main__':
    main()
