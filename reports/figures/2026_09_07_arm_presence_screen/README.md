# Superseded development preflight

Do not use this directory's scout scores or thresholds as the final experiment.
The PSS scout initially used the channel midpoint instead of the existing Standard
edge-dependent half-bin PSS reference.

The corrected experiment is in `../2026_09_07_arm_presence_screen_v2/`.
Its protocol binds these original development files by SHA-256. Only unchanged
GLRT, causal-cache, and dense-reference results were reused; their complete
receiver records were checked for equality after excluding the rerun scouts.
No held-out IQ was evaluated before correcting the PSS projection and freezing
the corrected development thresholds.
