# Donor-only element-age scale calibration

This is one frozen predictive arm. It does not read DS11 reference coordinates,
fit a position, or use DS11 residuals. The calibration population is the 25
donor units already exported from DS7--DS9. The transfer population is the nine
disjoint, fixed-endpoint target panels retained by the donor-residual study.

## Exact age and replay preflight

For every retained case, resolve the numerical bank's exact NORAD element from
the candidate manifest's pinned provider snapshots. Select the greatest tuple
`(element epoch, collected_utc_ns, snapshot digest)` and define age as capture
start minus that element epoch, in 86,400-second days. Bind the exact element
pair digest, provider snapshot occurrence, case identity, frozen residual
export, candidate bank, and endpoint. Whole-snapshot ages and current archive
contents are not substitutes.

Repropagate every donor case's selected element at its observation times and
the two timing nodes bracketing the frozen fitted timing. Require maximum bank
position error at most `1e-8 km`, velocity error at most `1e-10 km/s`, and
reconstructed residual error at most `1e-6 Hz`. All values must be finite and
all element epochs must precede capture. The existing target replay, bound by
digest, already requires zero-difference replay under the same limits; verify
each target element digest against it while deriving target age. Stop without
calibration if the preflight fails or exceeds 180 seconds.

## Frozen likelihoods and donor objective

Each retained case is one training-MAP candidate for one track. For residual
`r`, offset `c`, and scale `sigma`, use the normalized Student-t density with
four degrees of freedom:

`log p = lgamma(2.5)-lgamma(2)-0.5 log(4 pi)-log(sigma)-2.5 log(1+(r-c)^2/(4 sigma^2))`.

Profile one constant offset per case using training observations only and the
original weak `N(0, 1 MHz)` prior. The age arm is

Use the baseline's finite stationary-root procedure: quantile and zero starts,
fixed-point candidates, finite brackets around those candidates, Brent roots,
positive-curvature filtering, then the lowest located loss. At 100 Hz, replay
every retained offset and profiled training score against
`ds7_fast_baseline_adapter.profile`; any discrepancy above `1e-9 Hz` in offset
or `1e-9` in score stops the experiment. The finite brackets locate stationary
roots but are not a proof of the global minimum for arbitrary residual data;
preserve this limitation in the result.

`sigma(age;k) = sqrt(100^2 + (k age_days)^2) Hz`, `0 <= k <= 2000 Hz/day`.

`k=0` is exactly the original 100-Hz density. Fit the single `k` once on donor
training observations. For each case, divide its profiled training log score,
including its one offset-prior term, by its training count. Average cases
within physical source occasion `(session, NORAD, exact RF)`, source occasions
within scan, scans within dataset, then average DS7, DS8, and DS9 equally.

Fit one matched age-independent control on the same objective and population:
constant `10 <= sigma <= 5000 Hz`. This control has one fitted parameter, like
the age arm. No receiver-specific scale, age cutoff, alternative age law, or
coefficient sweep is permitted. Both optima must be finite, strictly interior
by at least `1e-4` of their parameter range, have numerical derivative at most
`1e-6` nats per parameter unit, and reproduce under a second finite-difference
step within `1e-5`. Preserve a failed or boundary fit as the result.

## Frozen held-transfer gate

At each target case, reprofile its offset from target training observations for
each frozen donor-fit arm, then score only held observations. The offset prior
does not enter the held increment. Normalize and aggregate in the same order:
held observations within case, cases within source occasion, sources within
scan, scans within dataset, and datasets equally.

The age arm passes only with complete target coverage and all of the following:

1. positive aggregate held gain over fixed 100 Hz separately in DS7, DS8, and
   DS9, plus improvement in a strict majority of paired source occasions;
2. positive aggregate held gain over the donor-fit constant-scale control
   separately in DS7, DS8, and DS9, plus improvement in a strict majority of
   paired source occasions;
3. qualified donor fits for both the age and constant models.

Report scan and source denominators, parameter estimates, boundaries, numerical
audits, and both paired comparisons. The target panels are previously exposed,
so a pass is a conditional predictive screen, not blind validation, satellite
identity validation, or geographic success. Prior RX-scale work improved a
scalar proxy but lost to a matched constant control under the actual contrast
likelihood; this protocol therefore requires the age relation itself to beat
the constant-scale control before any DS11 model is considered.

Run preflight and calibration as separate single-worker jobs with one BLAS
thread and a 180-second cap each. No RF collection, archive write, propagation
change, production edit, or geographic fit is authorized.
