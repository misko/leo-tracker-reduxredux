# Model B: Doppler-shape proposals

Status: implemented; five-recording shared-proposal development comparison
complete. This is an interim report; the full DS21 0.5 km target is unmet.

The proposal stage removes a constant offset from supported Doppler sequences
and matches their time variation to satellite predictions. Low-band, high-band
and all-band shape proposals join cold starts. Candidate discovery and
calibration are initialized at those proposals, then the final model fits
absolute CH1–8 frequencies. The final fit therefore retains freely fitted
receiver/band offsets and is not an offset-invariant shape-only estimator.

| Development recording | CH1–8 error km, fitted `c` |
| --- | ---: |
| DS21-001 | 2.492 |
| DS21-003 | 2.346 |
| DS21-005 | 1.272 |
| DS21-023 | 5.600 |
| DS21-039 | 8.600 |

Median 2.492 km; maximum 8.600 km; 0/5 below 0.5 km or 1 km. The proposals reduce
some earlier large-basin failures but do not resolve the shared model's position
error. Audits do not justify a tighter hardware-transfer prior or another simple
RF relabelling.

The separate [DS21-009 fitted-only comparison](../2026_10_13_ds21_release_readiness/THREE_MODEL_009_RESULTS.md)
completed 18 stationary absolute-frequency fits. All/low/high errors are
**5.327196 / 0.790354 / 0.772167 km**. Combining bands worsens position on this
case even though its all-band frequency loss is lower than Model A's. No view
meets 0.5 km. The selected all/high states carry timing-boundary flags; both
positions are inside their original 25 km search disks. Half-view likelihoods
use their designated observations but share discovery, proposal geography and
physical initialization, so they are not independent end-to-end pipelines.
Two all-band initial seeds needed independently verified exact source transfer
after strict projection nonconvergence; no failed solver result was accepted.
The historical five-case table and its aggregate statistics remain unchanged.

The current assigned investigation verifies native sky-RF scaling, clock
correction at actual receive times, and physical cross-view calibration
transport. It profiles local calibration directions against affine terms,
position and satellite timing. These fixed-responsibility diagnostics are not
confidence bounds or measurements of oscillator hardware.

See the [common progress report](README.md) for evaluation coverage, reference
limitations and the plan for full DS21. No locked evaluation result is claimed.
