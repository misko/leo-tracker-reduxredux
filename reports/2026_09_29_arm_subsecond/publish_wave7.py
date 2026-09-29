"""Archive Wave7 experiment evidence with immutable source/build bindings."""
import sys
from pathlib import Path
import publish_wave6

publish = publish_wave6.publish
publish.EXPERIMENTS += tuple('2026_09_29_arm_wave7_' + name for name in (
    'rank_histograms', 'coarse_overlap', 'proposal_budget', 'proposal_tracking',
    'certified_rank', 'float_final', 'budget_frontier', 'frontier_tracking',
    'proposal_tracking_fullcoarse', 'radius1', 'coarse_winograd',
    'coarse_winograd_integrated', 'compile_review', 'hist_pgo',
    'fullcoarse_radius1', 'codegen_matrix', 'frontier_pgo',
))

if __name__ == '__main__':
    publish.main()
    relative = Path('reports/2026_09_29_arm_fine_input_neon/tests')
    for name in ['test_fine_precision_tail_asan.c', 'run_tail_asan.sh', 'tail_asan.stderr']:
        publish.safe_copy(publish.REPORTS.parent/relative/name, Path(sys.argv[1])/relative/name)
    for experiment in ('2026_09_29_arm_wave6_pgo',
                       '2026_09_29_arm_wave6_combined_pgo',
                       '2026_09_29_arm_wave7_hist_pgo',
                       '2026_09_29_arm_wave7_frontier_pgo'):
        for source in (publish.REPORTS/experiment).glob('profile-data*.tar.gz'):
            publish.safe_copy(source, Path(sys.argv[1])/source.relative_to(publish.REPORTS.parent))
