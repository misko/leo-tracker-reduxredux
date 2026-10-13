# DS21-039 matched receiver RF contrast control

Status: specified before execution; no result is implied. This control follows
the [saved receiver RF score audit](RECEIVER_RF_SCORE_AUDIT.md). Opposing
receiver RF scores cancel at the stationary shared-coefficient solution.
They justify a model-sensitivity test, not a hardware-clock correction.

Both conditions fit the original common RF coefficient `c`. The baseline uses
the original model. The contrast condition appends one private nuisance `d`
with correction column `(RX0:+1, RX1:-1) * (RF - original RF center) / 1e9`.
Its effective coefficients are `c_RX0 = c + d` and `c_RX1 = c - d`, in Hz/GHz.
Every contrast fit starts at `d = 0`, uses bounds ±5000 Hz/GHz and optimizer
scale 200 Hz/GHz. There is no new Gaussian prior. This is not a `c = 0` arm.

Each condition gets exactly two initializers: the original all-band stationary
winner and the sealed seven-call refinement's training-selected free-position
winner. Physical vectors and original nuisance values are identical between
conditions. All four calls retain the original start-5 geographic center and
25-km disk, 20-second/600-iteration allowance, original 2,798 training windows,
43-satellite bank, native candidates/times, centering frames, and timing/group
priors applied once. The runner has a 165-second internal limit and external
termination/kill bounds of 175/180 seconds. It does not prepare held observations
or access a reference position.

Before fitting, zero contrast must reproduce both parent objectives and NLLs,
original gradients, and signal/clutter posteriors. The extra gradient must equal
the opposite-receiver RF directional derivative; its original-state sign and
magnitude are checked against the saved score audit. Synthetic tests check all
parameter gradients, prior accounting, and private receipt serialization.
The extra RF coefficient is explicitly labelled and must not be exported as a
group-clock coefficient through the old frozen-calibration interface.

Each condition selects its minimum-objective stationary result in the fixed
domain. The original stationary source states remain eligible only for the
unchanged baseline. They are not presumed stationary under the contrast model.
Every launch, termination, attempt, source snapshot and selection is retained;
failed calls are not silently retried. A selected bound-active contrast must
be reported explicitly.

Reference-position errors are joined only after all four outcomes and selections
are sealed. Report both conditions, including failures, fitted `c` and `d`,
objective/NLL/prior changes, convergence and position error. A frequency-fit
improvement does not establish localization improvement. A single development
case cannot establish full-DS21 performance; a supported improvement would
next need the other fixed development recordings and then all 34 development
members before a frozen release reaches the 20 locked CH1–8 recordings.
