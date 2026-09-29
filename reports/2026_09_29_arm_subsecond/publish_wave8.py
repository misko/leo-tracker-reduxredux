#!/usr/bin/env python3
"""Archive Wave8 evidence with immutable source/build bindings."""
import sys
from pathlib import Path

import publish_wave7

publish = publish_wave7.publish
publish.EXPERIMENTS += (
    '2026_09_29_arm_wave8_adaptive_q_glrt',
    '2026_09_29_arm_wave8_frontier_float_final',
    '2026_09_29_arm_wave8_frontier_rank_pgo',
    '2026_09_29_arm_wave8_gate_frontier',
    '2026_09_29_arm_wave8_gate_pgo',
    '2026_09_29_arm_wave8_integer_input',
    '2026_09_29_publication_source_audit',
    '2026_09_29_adaptive_glrt_audit',
)

original_excluded = publish.excluded
QUARANTINED = (
    Path('reports/2026_09_29_arm_wave8_adaptive_q_glrt/'
         'host32-unlabeled-preinstrumentation'),
    Path('reports/2026_09_29_arm_wave8_adaptive_q_glrt/'
         'host704-unlabeled-preinstrumentation'),
)


def excluded(path):
    """Exclude only the named stale cohorts in addition to inherited rules."""
    try:
        relative = path.resolve().relative_to(publish.REPORTS.parent.resolve())
    except ValueError:
        relative = path
    return original_excluded(path) or any(
        relative == cohort or cohort in relative.parents for cohort in QUARANTINED
    )


publish.excluded = excluded


if __name__ == '__main__':
    publish.main()
    destination = Path(sys.argv[1])
    relative = Path('reports/2026_09_29_arm_fine_input_neon/tests')
    for name in (
        'test_fine_precision_tail_asan.c',
        'run_tail_asan.sh',
        'tail_asan.stderr',
    ):
        publish.safe_copy(
            publish.REPORTS.parent / relative / name,
            destination / relative / name,
        )
    for experiment in (
        '2026_09_29_arm_wave6_pgo',
        '2026_09_29_arm_wave6_combined_pgo',
        '2026_09_29_arm_wave7_hist_pgo',
        '2026_09_29_arm_wave7_frontier_pgo',
        '2026_09_29_arm_wave8_frontier_rank_pgo',
        '2026_09_29_arm_wave8_gate_pgo',
    ):
        for source in (publish.REPORTS / experiment).glob('profile-data*.tar.gz'):
            publish.safe_copy(
                source,
                destination / source.relative_to(publish.REPORTS.parent),
            )
