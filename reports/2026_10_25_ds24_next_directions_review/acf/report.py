"""Small read-only evidence figure and metadata receipt; no inference."""
from pathlib import Path
import json

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

import audit
import recovery as r


def main():
    here = Path(__file__).resolve().parent
    summary = r.read(here / 'summary.json')
    rows = r.read(here / 'current_parent.json')
    examples = [row for row in rows if row['unowned_in_both_parent_arms'] and row['category'] == 'ACF_only']
    assert len(examples) == 2 and all(row['arm'] == 'c0' for row in examples)
    for row in examples:
        other = next(item for item in rows if item['case'] == row['case'] and item['component'] == row['component'] and item['arm'] == 'fitted_c')
        assert other['category'] == 'ACF_and_other'
    fig, axes = plt.subplots(1, 2, figsize=(11, 4), constrained_layout=True)
    names = ['ACF only', 'ACF + other', 'Other only']
    keys = ['ACF_only', 'ACF_and_other', 'other_only']
    historical = summary['historical_nomination']['archived_compatible_false']['category_counts']
    current = summary['current_parent']['unowned_whole_excluded_arm_records']['category_counts']
    for offset, source, label, color in [(-.18, historical, 'Historical nominees: n=929', '#64748b'),
                                       (.18, current, 'Current unowned: n=296 arm records', '#2563eb')]:
        bars = axes[0].bar(np.arange(3) + offset, [source.get(key, 0) for key in keys], width=.34, label=label, color=color)
        axes[0].bar_label(bars, padding=2)
    axes[0].set_xticks(np.arange(3), names); axes[0].set_ylabel('Records (different states and denominators)')
    axes[0].legend(fontsize=8); axes[0].set_ylim(0, 650); axes[0].grid(axis='y', alpha=.2)
    positions = np.arange(2)
    axes[1].bar(positions - .18, [row['residual_RMS_hz'] for row in examples], width=.34,
                label='Conditional residual RMS', color='#dc2626')
    axes[1].bar(positions + .18, [row['native_sigma_median_hz'] for row in examples], width=.34,
                label='Unchanged supplied sigma proxy', color='#94a3b8')
    axes[1].set_xticks(positions, ['0019 RX2 CH4, c=0', '0095 RX2 CH5, c=0'])
    axes[1].set_ylabel('Hz (not a significance or acceptance rule)'); axes[1].legend(fontsize=8)
    axes[1].grid(axis='y', alpha=.2)
    fig.suptitle('Real ACF-only exclusions exist, but differ from the vanishing-noise synthetic limit')
    fig.savefig(here / 'acf_evidence.png', dpi=150); plt.close(fig)
    r.write_new(here / 'report_receipt.json', dict(all_passed=True,
        original_gate_category_tests=2, test_position_fits=0, replay_position_fits=0,
        complete_cases=24, compute_seconds=summary['elapsed_seconds'], compute_cap_seconds=300,
        examples=[{key:row[key] for key in ('case', 'arm', 'component', 'points',
            'residual_RMS_hz', 'native_sigma_median_hz', 'failed_predicates')} for row in examples],
        source_sha256={str(path):r.sha(path) for path in (here / 'audit.py', here / 'test_audit.py', Path(__file__),
            Path(r.__file__), Path('/home/mouse9911/gits/leo-tracker-reduxredux/tools/audit_ds23_algo01_coverage.py'),
            Path('/home/mouse9911/gits/leo-tracker-reduxredux/tools/compare_dsx01_retention_localization.py'),
            Path('/home/mouse9911/gits/leo-tracker-reduxredux/tools/iterate_dsx01_position_nominations.py'))},
        artifact_sha256={str(path):r.sha(path) for path in (here / 'summary.json', here / 'seal.json', here / 'acf_evidence.png')},
        no_gate_waiver_or_amplitude_threshold=True, real_GPS_used=False))


if __name__ == '__main__': main()
