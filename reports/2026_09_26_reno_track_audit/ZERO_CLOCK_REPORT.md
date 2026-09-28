# Exactly zero timing offset at both diagnostic locations

For scan `scan-fw-d86e8f23c0624bac` (2026-09-26 12:50 UTC), evaluate the original full catalogue at the known receiver coordinates and the published wrong Reno coordinates. **Tau is exactly 0 seconds for every track at both locations.** Each track still independently selects a satellite and fits a constant frequency offset on training observations. No linear drift parameter is added. No Sacramento proposals, neighboring scans, or reference-seeded geographic search are used.

## Main comparison

Same 46 tracks and 892 occupied-second weight, same 800 Hz per-track cap and original evaluation observations as the previous comparison. Lower is better. Existing free/shared arms below use training-only identity/timing selection, matching the zero-offset arm's training-only identity selection.

| Timing model | Reference evaluation RMS | Wrong Reno evaluation RMS |
|---|---:|---:|
| Independent per-track tau, ±5 s | 294.88 Hz | 201.52 Hz |
| One fitted scan-wide tau, ±5 s | 483.19 Hz (tau -1 s) | 498.30 Hz (tau -4 s) |
| Exactly zero tau | **484.76 Hz** | **505.18 Hz** |

The zero-offset capped score favors reference by **20.42 Hz**, versus 15.11 Hz with a fitted scan-wide tau. Training scores at zero are 486.44 Hz reference and 504.73 Hz wrong Reno. Training and evaluation both favor reference under the pre-existing capped objective.

## Important cap sensitivity

| Zero-offset metric | Reference | Wrong Reno |
|---|---:|---:|
| Uncapped weighted evaluation RMS | **769.76 Hz** | **547.66 Hz** |
| Tracks exceeding the 800 Hz cap | 9/46 | 3/46 |
| Unmatched tracks | 0 | 0 |

Without the cap, the preference reverses to wrong Reno. A small number of much worse reference-location track fits are downweighted by the pre-existing cap; do not characterize this as an unqualified improvement or a robust location discriminator. The cap was not changed or selected based on this experiment.

Relative to independent per-track timing, zero timing changes 10/46 reference satellite assignments and 20/46 wrong-Reno assignments. Relative to fitted scan-wide timing, the changes are 6/46 and 32/46. This illustrates that identities can change substantially even when aggregate scores change only modestly.

As a separate fixed-identity sensitivity, keep each branch's original diagnostic identities and only refit its constant frequency offsets at zero timing. Capped evaluation RMS is 501.12 Hz reference versus 579.81 Hz wrong Reno. The main comparison above permits full-catalogue identity reassignment instead.

## Verification and limits

`evaluate_zero_clock.py` reads the immutable position document through the public storage port and checks document, evidence, and causal TLE snapshot digests against preceding experiments. It propagates at a singleton `[0.0]` timing grid and evaluates visibility at zero-offset epochs. Every selected tau is asserted to equal zero. `zero_clock_results.json` records all track identities, offsets, residuals, aggregate results, and source/previous-result hashes.

17 focused tests pass across the zero-clock, shared-clock, core, and audit suites. New checks verify that constant frequency offset remains fitted even with timing fixed to zero, that identity selection uses training rather than evaluation error, and that catalogue-block merging handles missing candidates and deterministic ties.

This is one selected failure with two fixed diagnostic sites and reused evaluation observations. Satellite identity ground truth is not independently known. No geographic search was rerun, so this does not establish reduced Reno location error. No production code, priors, persisted contracts, or RF collection changed.
