# Satellite PNT paired injection attempt 1 digest audit

Status: **NO-GO for downstream scoring.** The attempt-1 files remain immutable evidence of the execution and must not be rewritten or treated as the canonical paired injection result.

The single authorized run completed successfully and its outer manifest hashes close. It retained all 9,000 observation opportunities, used no future response for training, and made no identity or positioning claim. A post-run static audit nevertheless found that all six arm-level semantic digests fail to reproduce from the persisted JSON bytes.

The cause is presentation-only but material to reproducibility: the arm digest was computed from full-precision in-memory floats, while the JSON writer later applied `stable_measurement_floats`. The stored numerical values remain useful for diagnosing the run, and the three pair-level digests close because they bind the original arm-digest strings, but the arm payloads are not self-authenticating.

The exact failure inventory is frozen in [the machine-readable digest audit](figures/2026_08_27_satellite_pnt_cross_family_injection_attempt1-digest-audit.json). A corrective attempt requires a separately committed amendment, new exclusive paths, and a static digest-closure test before any downstream model comparison. No scientific model, truth trajectory, IQ source, measurement setting, or result interpretation may change under that correction.
