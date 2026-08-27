# Satellite PNT cross-family predictive scoring attempt 1 determinism audit

Status: **NO-GO for a canonical predictive result.** The attempt-1 report and JSON remain immutable execution evidence and must not be reinterpreted as the final scoring artifact.

The displayed leave-one-background-pair-out conclusion is stable: the primary model-family preference matches 3/6 truth arms (50%), and no threshold or identity claim is supported. However, the semantic result digest changes with the OpenBLAS thread count because the implementation formed and factorized dense future covariance matrices. Algebraically equivalent parallel reductions differ at the last floating bits, which is unacceptable for a hash-sealed result.

The exact digest variants and attempt-1 file hashes are frozen in [the machine-readable audit](figures/2026_08_27_satellite_pnt_cross_family_predictive_scoring_attempt1-determinism-audit.json). A corrective attempt may only replace the dense calculation with an algebraically equivalent deterministic diagonal-plus-low-rank calculation, must preserve the frozen data/model design and attempt-1 bytes, and must write new exclusive outputs. No IQ needs to be reopened.
