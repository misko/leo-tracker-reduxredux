"""Publish completed fifth-wave experiments and retain earlier failure evidence."""
import publish_wave4
from pathlib import Path
import sys

publish = publish_wave4.publish
publish.JSON_NAMES.update({'cpu-distribution.json', 'source-bindings.json'})
original_excluded = publish.excluded

def excluded(path):
    # This directory is an unqualified reconstruction, not the original
    # diagnostic build. Preserve the original cohort receipt and its exact
    # source archive instead; never publish inconsistent reconstruction files.
    return original_excluded(path) or (
        '2026_09_29_arm_peak_select_fast' in path.parts and 'builds-v1' in path.parts)

publish.excluded = excluded
publish.EXPERIMENTS += (
    '2026_09_29_arm_coarse_gate_frontier',
    '2026_09_29_arm_rate_coarse_gate',
    '2026_09_29_arm_rate_gate_transfer',
    '2026_09_29_arm_conditioned_wide_blocks',
    '2026_09_29_arm_conditioned_quadratic',
    '2026_09_29_arm_conditioned_low_order',
    '2026_09_29_arm_conditioned_sample_neon',
    '2026_09_29_arm_half_rate_analysis',
    '2026_09_29_arm_decimated_fine_neon',
    '2026_09_29_arm_decimated_fine_neon_diagnostic',
    '2026_09_29_arm_decimated_fine_neon_diagnostic_v2',
    '2026_09_29_arm_wave5_candidate',
    '2026_09_29_arm_gate_quadratic',
    '2026_09_29_arm_peak_select_fast',
    '2026_09_29_arm_direct_ci16_ingest',
    '2026_09_29_arm_wave5_combined',
    '2026_09_29_arm_wave5_profile',
    '2026_09_29_arm_sparse_peak_scan',
    '2026_09_29_arm_direct_ci16_prefix',
    '2026_09_29_arm_wave5_sparse_combined',
    '2026_09_29_arm_wave5_final',
)

if __name__ == '__main__':
    publish.main()
    relative = Path('reports/2026_09_29_arm_fine_input_neon/tests')
    for name in ['test_fine_precision_tail_asan.c', 'run_tail_asan.sh', 'tail_asan.stderr']:
        publish.safe_copy(publish.REPORTS.parent/relative/name, Path(sys.argv[1])/relative/name)
