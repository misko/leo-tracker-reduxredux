# Independent review

Reviewed the sealed audit result (SHA-256
`495c61a73027ec498b8e7adcd80be981ed2a705a130145debaafa725f1b87c13`),
audit source (SHA-256
`d96a3008fb9a5d78b234e9d7a568cf9431932280bf47678b3be1c73388496fc0`),
and its bound paired-residual, strict-metadata, and production sources. The
artifact is TRAIN-only and records no reference, validation, TEST, or position
refit use.

The source-derived convention findings are supported: edge selects pilot
template/bins rather than changing the CFO sign, GLRT reports tracking CFO as
acquisition plus residual, RF projection subtracts IF offset for both edges,
and trajectory normalization uses a positive RF ratio. The time-confounding
summary correctly shows unequal edge support, only five within-session
comparisons, and should remain descriptive rather than causal.

The synthetic validation is insufficient for the stronger sign/slope-recovery
claim. Every current injection seeds `acquired_cfo_hz` at exactly the injected
instantaneous CFO, so every residual is mechanically zero. Although the report
describes two time-separated chirp probes, all calls use the default
`time_offset_s=0`. Add both positive and negative nonzero acquisition-seed
offsets for each edge, plus at least two nonzero chirp windows with the expected
tracking-CFO change. Preserve this output as preliminary/superseded for that
synthetic claim. Until then, it supports source-convention inspection and no
edge-causality or shared-drift conclusion.

## Corrected synthetic audit

The corrected result is approved. It binds source
`ecc685e21c50281312acaf0fa987e6af07a1e6925a34407f04517ecaef8cf17b` and
sealed result `adf217ec6efca4846d7bf7c65f01c8914d8a356d4d6f6ce9a3496849c1c5cc6d`;
the sidecar matches. The five focused tests and Ruff pass.

For both edges, the +42/-42-kHz injections now use seeds offset by 1.5 kHz and
recover residuals with the expected sign (about +/-1.332 kHz), yielding tracking
CFO within 200 Hz of injection. The residual shortfall is consistent with the
finite GLRT frequency grid and is stated as such. The -1.8-kHz/s chirp now
uses 0- and 1-second windows: both edges recover the same -1.776-kHz/s change.
These are synthetic inputs, not truth or a hardware calibration.

This resolves the convention test gap. It does not change the limited corpus
interpretation: the edge/time statistic remains confounded and the five
within-session comparisons cannot establish edge causality or authorize a
receiver-drift correction.
