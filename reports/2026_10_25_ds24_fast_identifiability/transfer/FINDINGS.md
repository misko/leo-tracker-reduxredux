# Chronological predictive-prior transfer: mixed gains, no operational change

The first four eligible archived sources produce two improvements and two
geographic regressions in **both** c arms. All eight fits are numerically
qualified, but 0011 c=0 fails preservation of the original complete accepted-ID
ledger. The predictive role therefore does not guarantee safe movement.
Every target remains an unqualified experimental factor and every operational
output remains its exact saved baseline.

## Frozen selection and ownership

The prior metadata inventory had 97 provisional rejected graph bindings and
zero fully certified ownership ledgers. This wave reconstructed complete parent
accepted IDs, including postfit-only extensions, at unchanged saved positions
and phase references. No position fit, fresh nomination or GPS/error lookup was
used for selection. Reconstruction took 15.876 s.

The first eligible source in each of the first four eligible distinct scans,
ordered by recording UTC, scan ID, original source ID and component, was frozen:

| Scan | Archived modeled family | Original source | Alias | Points |
| --- | ---: | --- | ---: | ---: |
| 0010 | 64023 | RX1 CH1 T001 | 0 | 50 |
| 0011 | 58175 | RX1 CH1 T006 | 1 | 20 |
| 0012 | 57743 | RX1 CH2 T001 | 1 | 59 |
| 0013 | 60108 | RX1 CH2 T005 | 1 | 53 |

All have original active-curvature eligibility, whole native-ID ownership,
inactive parent-likelihood families and zero overlap with either arm's complete
accepted IDs. They remain **archived rejected nominees**, not screened recovery
proposals or validated satellite associations. All four happen to be RX1 low
band; this panel does not establish receiver/band-wide transfer.

## Matched likelihood and checks

The unchanged R2 implementation scores the target predictive-only, jointly with
original predictive evidence under the parent curved posterior. The full
original physical-mode covariance includes level/phase-like components. Target
CFO does not update fixed-position parent calibration, noise or phase references.
The causal Student nu=3 distribution uses its original parameters before
conditioning on [-15,+15] seconds; no variance or prior tuning occurred.

All **80** fixed branch positions passed the frozen 1281-node check against
2561 nodes and independent adaptive integration. Maximum preflight score and
gradient errors were 1.81e-5 and 3.62e-5 objective/km, below 1e-3. Fixed-position
target-redaction checks pass. At the final parent references, maximum endpoint
errors were 1.10e-5 and 2.81e-5 objective/km. No case was retuned or replaced.

Three owned tests pass. Original `r.valid` residual/support/visibility, finite
region and unclipped absolute-phase predicates are reused, with Gamma
convergence and both accepted/likelihood ID preservation. All original parent
likelihood IDs remain in all eight fits. Seven arms pass every parent check.

## Post-seal geographic results

Geography was added only after [RF sealing](RF_seal.json), using the same fixed
reporter position and distance convention as R2. Errors below are kilometres.

| Scan | c=0 baseline → diagnostic | Fitted-c baseline → diagnostic | Parent qualification |
| --- | ---: | ---: | --- |
| 0010 | 1.241914 → 1.281393 | 1.246473 → 1.319167 | Both pass |
| 0011 | 1.727732 → 1.413449 | 1.567029 → 1.311278 | c=0 fails accepted-ID preservation |
| 0012 | 1.730910 → 1.356137 | 1.941516 → 1.505699 | Both pass |
| 0013 | 0.791529 → 0.863169 | 0.863389 → 0.897052 | Both pass |

Raw all-attempt mean errors change 1.373021→1.228537 km (c=0) and
1.404601→1.258299 km (fitted c). These means **include the unqualified 0011 c=0
endpoint** and are not operational policy gains. The geographically favorable
0011 c=0 movement loses 21 original postfit-compatible IDs from RX1 CH4 T007
(modeled57955) and eight from RX1 CH8 T000 (modeled68031). Curved/predictive
training gates and exact likelihood membership still pass. The complete ledger
guard catches a failure that a likelihood-only ownership check would miss.

0010 lowers parent curved RMS by only 0.008/0.012 Hz while geographic errors
worsen by 39/73 m. In 0012, geographic errors improve by 375/436 m while parent
curved RMS rises by about 0.018 Hz. Frequency fit and geographic accuracy remain
separate outcomes; none of these effects validate the new identities.

## Runtime, figures and limits

The complete scientific run, including preflight and final endpoint checks,
took **143.745 s wall time**. Eight fits took 13.417–28.909 s each, summed worker
time171.356 s, within 180 s/arm and 1200 s globally. Two workers used one numeric
thread each. There were no retries, timeouts, rescues, new candidates or backfill.

- [Geographic outcomes, including the accepted-ID preservation failure](figures/geographic_transfer_caption02.png).
- [Zero/prior target gradient influence at fixed baseline positions](figures/fixed_target_gradients.png).
- [Native-ID-aligned source CFO views](figures/target_native_cfo.png).
- [Descriptive phase-marginal residuals](figures/target_residuals.png).

All four figures were visually inspected. Native coordinates are checked by
ID and prediction-plus-residual closure. Residuals omit target-local constant
and shape posterior mean adjustments; target data condition phase, so these
are neither held-out prediction nor full-fit RMS.

The geographic caption has a separately versioned reporting-only clarification:
hatching marks failure to preserve original accepted IDs; every target identity
remains unqualified independently. Original figures and RF artifacts are preserved.

See [panel](panel.json), [protocol](protocol.json), [ownership](ownership/),
[preflight results](preflight_results.json), [all attempts](execution_result.json),
[exact evaluation CSV](evaluation.csv), [evaluation summary](evaluation_summary.json)
and [report seal](report_seal.json), plus the [caption clarification seal](report_caption02_seal.json). New targets contribute experimental
likelihood inputs only: **zero new accepted target associations**. This is a
small, previously exposed same-site panel, not a new-location test or ALGO
promotion. No further inference or cohort expansion was performed.
