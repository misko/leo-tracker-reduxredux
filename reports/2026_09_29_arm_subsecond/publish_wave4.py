"""Extend the completed experiment publication with fourth-wave evidence."""
import publish_wave3
from pathlib import Path
import sys

publish = publish_wave3.publish
publish.EXPERIMENTS += (
    '2026_09_29_arm_proposal_preplan',
    '2026_09_29_arm_proposal_rank_fast',
    '2026_09_29_arm_proposal_rank_fast_v2',
    '2026_09_29_arm_wave4_float_fft',
    '2026_09_29_arm_fine_input_neon',
    '2026_09_29_arm_conditioned_order_neon',
    '2026_09_29_arm_coarse_epoch4',
    '2026_09_29_arm_wave4_combined',
)

if __name__ == '__main__':
    publish.main()
    # Preserve the rejected prototype's independent failure reproducer too.
    # Its sealed implementation is already retained in the source archives.
    relative=Path('reports/2026_09_29_arm_fine_input_neon/tests')
    for name in ['test_fine_precision_tail_asan.c','run_tail_asan.sh','tail_asan.stderr']:
        publish.safe_copy(publish.REPORTS.parent/relative/name,Path(sys.argv[1])/relative/name)
