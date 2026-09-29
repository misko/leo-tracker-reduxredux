"""Counterfactual quality only; this does not measure native gated runtime."""
import copy
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent/'2026_09_28_arm_full_optimization'))
import independent_summary as frozen


def gated_candidate(candidate, threshold):
    result = dict(candidate)
    skipped = bool(candidate['conditioned_fallback'] and
                   candidate['pre_exact']-candidate['pre_control'] < threshold)
    if skipped:
        result.update(exact_score=candidate['pre_exact'],
                      control_score=candidate['pre_control'],
                      margin=candidate['pre_exact']-candidate['pre_control'],
                      acquired_cfo_hz=candidate['pre_acquired'],
                      tracking_cfo_hz=candidate['pre_tracking'],
                      conditioned_fallback=False, conditioned_cfo_hz=None,
                      conditioned_score=None)
    result['epoch'] = result['refined_epoch']
    return result, skipped


def main():
    cohort = HERE/'host704-instrumented'
    manifest = json.loads((cohort/'manifest.json').read_text())
    assert manifest['complete']
    assert frozen.sha256(cohort/'rows.jsonl') == manifest['rows_sha256']
    standard_path = HERE.parent/'2026_09_28_ds7_large_arm/baseline-01/rows.jsonl'
    baseline = frozen.load_baseline(standard_path)
    original = frozen.load_native(cohort/'rows.jsonl')
    control_path = HERE.parent/'2026_09_29_arm_fused_pipeline/host704-v4/rows.jsonl'
    control = frozen.load_native(control_path)
    assert original.keys() == control.keys()
    checked = 0
    for case, windows in original.items():
        for key, row in windows.items():
            expected = control[case][key]['candidates']
            assert len(row['candidates']) == len(expected)
            for candidate, ref in zip(row['candidates'], expected):
                assert all(candidate[k] == value for k, value in ref.items())
                if not candidate['conditioned_fallback']:
                    assert candidate['pre_exact'] == candidate['exact_score']
                    assert candidate['pre_control'] == candidate['control_score']
                    assert candidate['pre_tracking'] == candidate['tracking_cfo_hz']
                checked += 1
    results = []
    for threshold in [-1.0, -.1, -.05, -.025, 0.0, .005, .01, .02, .025, .04,
                      .05, .075, .1, .15, .2, .3, .5, 1e9]:
        native = copy.deepcopy(original)
        skipped = fallbacks = 0
        for windows in native.values():
            for row in windows.values():
                candidates = []
                for candidate in row['candidates']:
                    fallbacks += bool(candidate['conditioned_fallback'])
                    changed, skip = gated_candidate(candidate, threshold)
                    candidates.append(changed)
                    skipped += skip
                row['candidates'] = candidates
        quality = frozen.summarize(manifest['selected'], baseline, native)
        result = {'threshold': threshold, 'logical_fallbacks': fallbacks,
                  'logical_fallbacks_skipped': skipped, 'quality': quality}
        results.append(result)
        print(threshold, skipped, quality['totals']['recovered_positive_hits'], flush=True)
    output = {'scope': 'counterfactual recovery; no runtime or native gate claim',
              'unchanged_control_candidates_checked': checked,
              'input_sha256': manifest['rows_sha256'],
              'standard_sha256': frozen.sha256(standard_path),
              'matcher_sha256': frozen.sha256(Path(frozen.__file__)),
              'runner_sha256': frozen.sha256(Path(__file__)),
              'results': results}
    (HERE/'replay-results.json').write_text(json.dumps(output, indent=2)+'\n')


if __name__ == '__main__':
    main()
