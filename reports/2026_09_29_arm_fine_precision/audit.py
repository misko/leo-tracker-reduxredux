"""Score experimental fine FFT outputs against sealed standard GLRT detections."""
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
    args = p.parse_args()
    folder = args.cohort
    manifest = json.loads((folder/'manifest.json').read_text())
    assert manifest['complete']
    assert frozen.sha256(folder/'rows.jsonl') == manifest['rows_sha256']
    selected = manifest['selected']
    baseline_path = HERE.parent/'2026_09_28_ds7_large_arm/baseline-01/rows.jsonl'
    baseline = frozen.load_baseline(baseline_path)
    native = frozen.load_native(folder/'rows.jsonl')
    cases = {(c['session_id'], c['visit_index']) for c in selected}
    assert len(cases) == len(selected) == manifest['processed_dwells']
    assert set(native) == cases
    # Native reports refined_epoch; frozen matching consumes epoch.
    for windows in native.values():
        for row in windows.values():
            for candidate in row['candidates']:
                candidate['epoch'] = candidate['refined_epoch']
    result = frozen.summarize(selected, baseline, native)
    for group in [result['totals'], *result['by_rate'].values()]:
        group['unmatched_positive_hits'] = group['native_positive_hits']-group['recovered_positive_hits']
        group['hit_recovery_fraction'] = group['recovered_positive_hits']/group['reference_positive_hits'] if group['reference_positive_hits'] else None
    result.update(baseline_sha256=frozen.sha256(baseline_path),
                  native_sha256=frozen.sha256(folder/'rows.jsonl'),
                  manifest_sha256=frozen.sha256(folder/'manifest.json'),
                  matcher_sha256=frozen.sha256(Path(frozen.__file__)),
                  gate={'margin': .025, 'epoch_samples': 2, 'tracking_cfo_hz': 8000})
    (folder/'standard-audit.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result['totals'], indent=2))


if __name__ == '__main__':
    main()
