"""Publish completed second-wave evidence using the existing hash verifier."""
import publish

publish.EXPERIMENTS += (
    '2026_09_29_arm_folded_fine_fft',
    '2026_09_29_arm_batched_fine_fft',
    '2026_09_29_arm_q15_glrt_dot',
    '2026_09_29_arm_neon_moments',
    '2026_09_29_arm_fused_pipeline',
)

if __name__ == '__main__':
    publish.main()
