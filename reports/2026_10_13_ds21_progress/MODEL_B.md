# Model B: Doppler-shape proposals

Status: implemented; five-recording shared-proposal development comparison
complete. This is an interim report; the full DS21 0.5 km target is unmet.

The latest [DS21-009 fixed-policy coverage transfer](../2026_10_13_ds21_release_readiness/COVERAGE_THREE_MODEL_009_RESULTS.md)
completed 18 stationary B fits. All/low/high errors are
**0.436419 / 0.940492 / 4.181058 km**, versus the original
**5.327196 / 0.790354 / 0.772167 km**. CH1–8 now passes 0.5 km and beats both
halves on this recording, while both half-band errors worsen. Training selects
`shape-all` for CH1–8; all selected boundary flags are false. This is one
successful development case, not a full-DS21 release or a reason to select B
by each recording's reference error.

The earlier [DS21-013 coverage-conditioned comparison](../2026_10_13_ds21_release_readiness/COVERAGE_THREE_MODEL_013_RESULTS.md)
completed 18 stationary B fits. All/low/high errors are
**2.021218 / 2.895507 / 7.808977 km**, versus the original
**268.879362 / 268.826502 / 190.851447 km**. Combining improves on both halves
for this control, but every view misses 0.5 km. All three selected boundary flags
are false. The discovery change propagates into candidate and physical-seed
initialization; it does not isolate a single downstream mechanism or establish
cross-case transfer. Historical results remain unchanged.

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

The subsequent [DS21-011 comparison](../2026_10_13_ds21_release_readiness/THREE_MODEL_011_RESULTS.md)
completed 18 stationary B fits. All/low/high errors are
**0.743996 / 1.142057 / 6.735033 km**, with no selected physical boundary flags.
Combining improves on both halves here, unlike 009, but still misses 0.5 km.
All required initialization projections succeeded with the original strict
solver; no fallback was needed. The shared initialization caveat remains.

The subsequent [DS21-013 comparison](../2026_10_13_ds21_release_readiness/THREE_MODEL_013_RESULTS.md)
completed 18 stationary B fits, but all/low/high errors are
**268.879362 / 268.826502 / 190.851447 km**. All selected physical boundary
flags are false; training selects `cold-0` for all/low and `cold-1` for high.
One unselected B/all `shape-low` initialization uses independently certified
exact source transfer after strict projection nonconvergence, with maximum
closure 7.276e-12 Hz. Six carried clock coefficients are only 4.55e-13 Hz inside
the -2000 Hz bound; its empty exact-equality active list does not establish
substantial interior margin. The shared position failure is not attributed
to this seed fallback. The configured reference is inside the regional prior
but outside all six fixed local disks; their nearest gap is 157.457260 km
in optimizer coordinates.
This coverage failure requires a reference-blind discovery control before
further rollout. No new tolerances, retries or source changes were used.

The current assigned investigation verifies native sky-RF scaling, clock
correction at actual receive times, and physical cross-view calibration
transport. It profiles local calibration directions against affine terms,
position and satellite timing. These fixed-responsibility diagnostics are not
confidence bounds or measurements of oscillator hardware.

See the [common progress report](README.md) for evaluation coverage, reference
limitations and the plan for full DS21. No locked evaluation result is claimed.
