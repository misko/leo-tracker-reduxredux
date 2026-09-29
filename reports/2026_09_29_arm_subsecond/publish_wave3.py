"""Publish only completed third-wave experiments and their source receipts."""
import publish_wave2

publish = publish_wave2.publish
publish.EXPERIMENTS += (
    '2026_09_29_arm_rank_only_proposal',
    '2026_09_29_arm_resampled_omit_fused',
    '2026_09_29_arm_cached_float_dot',
    '2026_09_29_arm_boundary_gate',
    '2026_09_29_arm_wave3_combined',
    '2026_09_29_arm_crosswindow_cache_potential',
    '2026_09_29_arm_two_lag_proposals',
    '2026_09_29_arm_single_lag_proposals',
    '2026_09_29_arm_adaptive_fine_fft',
    '2026_09_29_arm_decimated_fine_fft',
    '2026_09_29_arm_coarse_score_gate',
    '2026_09_29_arm_fine_fft_packing_review',
    '2026_09_29_arm_wave3_unroll',
    '2026_09_29_arm_native_coarse_gate',
)

if __name__ == '__main__':
    publish.main()
