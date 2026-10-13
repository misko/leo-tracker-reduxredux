# DS21-039: completed four-direction diagnostic

The corrected diagnostic completed in **38.73 seconds**, with **zero optimizer
calls**, using the original fitted-`c` training winners and 43-satellite bank.
All three saved objectives and likelihoods replay exactly. All 13 output receipts
and the 319-file scientific source snapshot passed final checks. No held data or
reference position was used for these calculations.

This establishes diagnostic evidence, not a localization improvement. The existing
CH1–8 position error remains 4.291 km; the 0.5 km target is unmet. The prescribed
18 fixed-position nuisance fits are the next experiment.

## Findings in priority order

**1. Optimization still needs the prescribed profile test.** Replaying the saved
solutions succeeded exactly, so numerical drift in today's implementation does
not explain their differences. The full model's likelihood is 32,969.50 and its
prior cost is 202.92, mostly relative satellite timing. A replay alone cannot
show whether a better joint optimum was missed. Profiles at the three original
training-selected positions will test that question with matched starts and
unchanged observations, priors and candidate bank.

**2. RF scaling is correct; calibration changes are coupled to the fitted
physical state.** The largest RF-scaling discrepancy is 1.16e-10 Hz. Native
receive-time and clock-design checks close exactly. Yet half-band and all-band
physical correction functions differ by 77–102 Hz RMS on the same native
observations. After projecting out other physical prediction directions, only
10.55% of the all-band `c` column's squared norm remains. This is a conditional
local design diagnostic, not a confidence estimate or a measured hardware error.
The fitted timing RMS is approximately 4.6–5.2 seconds across the three views.

**3. Combining changes assignments as well as calibration.** On exactly matching
native observations, the satellite-or-clutter maximum-posterior assignment changes
in 310/1,692 low-band windows (18.3%) and 225/1,106 high-band windows (20.3%). These
assignments are conditional model hypotheses, not verified transmitter identities.

The following likelihood costs compare four frozen states within each band;
lower is better. “Geometry” includes satellite timing. Every row in a column uses
the same observations, native candidate IDs and normalized prior.

| Geometry/timing | Physical correction | CH1–4 NLL | CH5–8 NLL |
| --- | --- | ---: | ---: |
| All-band | All-band | 20,075.96 | 12,893.54 |
| Half-band | All-band | 19,925.12 | 13,536.48 |
| All-band | Half-band | 20,359.69 | 13,045.54 |
| Half-band | Half-band | 19,619.15 | 13,372.12 |

Substituting the half-band calibration alone worsens both bands at the all-band
geometry/timing state. The low band's own combined state is better by 456.81 NLL,
whereas the high band prefers the full-model state by 478.58 NLL. Thus simply
transferring a learned shift cannot be assumed to preserve the fit that produced
it. Geometry, timing, calibration and assignments interact.

The original cell-winner adapter also retains 3,714 of 7,622 passing native
alternatives and discards 3,908. There are 913 collision cells whose frequency
spread exceeds the model's residual scale. Earlier candidate-preservation controls
had mixed localization results on other recordings, so this loss is evidence to
investigate, not sufficient grounds to promote that change.

**4. Weight imbalance exists but these fixed-state rankings survive block
balancing.** Low-band observations comprise 60.47% of the 2,798 windows; the larger
receiver contributes 64.01%. Across 12 training blocks, the largest block supplies
11.22% of windows and 11.11% of signal mass. These proportions do not show a single
block dominating the entire observation inventory. They do not estimate the
number of independent measurements.

| Half state minus full state, mean window NLL | Equal window weights | Equal block weights |
| --- | ---: | ---: |
| Low-band comparison | −0.26998 | −0.25508 |
| High-band comparison | +0.43271 | +0.25231 |

Block balancing reduces the high-band preference substantially but does not
reverse either comparison. Priors are excluded here; these are frozen likelihood
sensitivities, not new optimized objectives or position results. Each comparison
contains one band, so equal-band weights coincide with equal-window weights.

## Debugging and validation

The first run is preserved as failed. Three almost-certain-clutter windows had
positive signal masses as small as 5e-324. Multiplying by residuals before
conditioning caused rounded moments to violate the mean/RMS consistency check.
The repair conditions native weights first, preserving likelihoods, posterior
probabilities, signal/clutter masses and zero-signal handling. It neither clips
small probabilities nor changes a position fit. Thirteen new subnormal regression
cases cover this failure.

A bounded low-view debug replay additionally identified the native binary as a
late-loaded source. The corrected freeze explicitly preloads and archives it.
The failed first run, debug receipts and their original source snapshots remain
unchanged. The completed second run has full before/after source validation.

The four diagnostic components and actual synthetic pipeline have 69 passing
focused tests. The separately implemented profile runner has eight passing
component tests, including cached fixed-position and single-launch guards.

## Next decision and acceptance

Complete the 18 prescribed profiles before changing the calibration model or
timing prior. A lower feasible objective at a half-band anchor would establish
that the original all-band search missed a better state. A worse result at those
anchors would not establish a global optimum or a correct position.

Evidence currently puts calibration/association interaction ahead of a missing
RF frequency factor or simple count imbalance. Any proposed correction must
improve sealed position results across development recordings, then pass the
frozen full-DS21 evaluation described in the [plan](README.md). Frequency-fit
improvement alone is insufficient, and no 0.5 km result is claimed here.

## Bindings

Full receipts are retained locally under `local/diagnostics-v2`.

- Protocol SHA-256: `d6ac7aa2e9b9fc32c9c1cb1713cc8a4b3ac1b63e167671ba5c56fae138c3fd52`.
- Complete terminal SHA-256: `1e082d95de47715ef600d000adb9b89dbd4f722bda7b33754b560aa0388f15aa`.
- Objective replay SHA-256: `1d0afbc3cc65d05687ab796615452b44f57e4aa101c8e6e54f1daca58e8fd77e`.
- Weighting comparisons SHA-256: `9881f8cda6946b2b299f2095fa224262cb7081c8175f9101a919b95f057a60db`.
