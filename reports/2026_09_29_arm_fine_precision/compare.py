"""Compare candidate decisions and standard recovery per window, not just totals."""
import argparse
import json
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'2026_09_28_arm_full_optimization'))
import independent_summary as frozen


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--cohort', type=Path, required=True)
    p.add_argument('--reference', type=Path, required=True)
    a = p.parse_args()
    baseline_path = HERE.parent/'2026_09_28_ds7_large_arm/baseline-01/rows.jsonl'
    baseline = frozen.load_baseline(baseline_path)
    current = frozen.load_native(a.cohort/'rows.jsonl')
    previous = frozen.load_native(a.reference/'rows.jsonl')
    counts = dict(windows=0, candidate_entries=0, changed_positive_decisions=0,
                  changed_window_recovery_counts=0, changed_coarse_candidates=0)
    maxima = dict(margin=0., acquired_cfo_hz=0., tracking_cfo_hz=0.)
    for case, windows in current.items():
        for key, row in windows.items():
            counts['windows'] += 1
            old = previous[case][key]
            expected = [c for c in baseline[case][key]['candidates'] if c['margin'] >= .025]
            totals = [frozen.maximum_matches(expected, [c for c in v['candidates'] if c['margin'] >= .025]) for v in (old, row)]
            counts['changed_window_recovery_counts'] += totals[0] != totals[1]
            for x, y in zip(row['candidates'], old['candidates'], strict=True):
                counts['candidate_entries'] += 1
                counts['changed_positive_decisions'] += (x['margin'] >= .025) != (y['margin'] >= .025)
                counts['changed_coarse_candidates'] += (x['coarse_epoch'], x['coarse_bin']) != (y['coarse_epoch'], y['coarse_bin'])
                for field in maxima:
                    maxima[field] = max(maxima[field], abs(x[field]-y[field]))
    result = {'counts': counts, 'maximum_ordered_deltas': maxima,
              'reference_sha256': frozen.sha256(a.reference/'rows.jsonl'),
              'native_sha256': frozen.sha256(a.cohort/'rows.jsonl'),
              'standard_baseline_sha256': frozen.sha256(baseline_path)}
    (a.cohort/'precision-comparison.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
