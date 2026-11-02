"""Compare sealed RF decisions with PREVIOUS full-data position outcomes.

This script never fits a position or changes a decision. The five-case panel is
development evidence, deliberately chosen to include prior gains/regressions.
"""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parent
OLD = ROOT.parent / '2026_11_02_family_reliability/population/positions.csv'


def main():
    sealed = (ROOT / 'decisions.json').read_bytes()
    digest = hashlib.sha256(sealed).hexdigest()
    assert digest == (ROOT / 'decisions.sha256').read_text().split()[0]
    decisions = json.loads(sealed)['cases']
    old = list(csv.DictReader(OLD.open()))
    rows = []
    for case, decision in decisions.items():
        for arm in ['c0', 'fitted_c']:
            source, = [r for r in old if r['case'] == case and r['arm'] == arm]
            baseline = float(source['baseline_error_m']) / 1000
            candidate = float(source['selected_error_m']) / 1000
            rows.append(dict(case=case, arm=arm, previous_ALGO07_error_km=baseline,
                previous_SD4_error_km=candidate, RF_verdict=decision['verdict'],
                strict_abstention_previous_policy_error_km=baseline,
                associated_points_before=int(source['baseline_associated']),
                associated_points_after=int(source['selected_associated'])))
    with (ROOT / 'retrospective.csv').open('w') as stream:
        writer = csv.DictWriter(stream, rows[0].keys())
        writer.writeheader(); writer.writerows(rows)
    (ROOT / 'retrospective_binding.json').write_text(json.dumps(dict(
        decisions_sha256=digest, previous_positions_source=str(OLD),
        previous_positions_sha256=hashlib.sha256(OLD.read_bytes()).hexdigest(),
        scope='Retrospective comparison with previously published full-data outcomes; '
              'no new localization, no independent validation, no GPS selection',
        strict_abstention_preserves_all_five_previous_ALGO07_outputs=True), indent=2)+'\n')
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.9), sharey=True)
    cases = list(decisions)
    for ax, arm in zip(axes, ['c0', 'fitted_c']):
        data = [r for r in rows if r['arm'] == arm]
        x = np.arange(len(data))
        ax.bar(x-.18, [r['previous_ALGO07_error_km'] for r in data], .36,
               color='#406d9b', label='Previous ALGO07')
        ax.bar(x+.18, [r['previous_SD4_error_km'] for r in data], .36,
               color='#d99a40', label='Previous SD×4 candidate')
        ax.set_xticks(x, cases, rotation=30, ha='right')
        ax.set_title('c = 0' if arm == 'c0' else 'Fitted c')
        ax.set_ylabel('Previously measured position error (km)')
        ax.grid(axis='y', alpha=.2); ax.set_axisbelow(True)
    axes[0].legend(fontsize=9)
    fig.suptitle('Earlier full-data outcomes on the five-case challenge panel')
    fig.text(.5, .015, 'New strict predictive test abstains on all five; these bars are not new holdout-fit errors.', ha='center', fontsize=10)
    fig.tight_layout(rect=(0,.045,1,.95))
    fig.savefig(ROOT/'previous_position_outcomes.png', dpi=170)
    plt.close(fig)
    print('Five retrospective comparisons bound to RF decision seal', digest)


if __name__ == '__main__':
    main()
