# Pre-outcome review: short-horizon orbital increment likelihood

## Decision

The proposed likelihood is a proper causal conditional density if the history and normalization
rules below are implemented literally. It tests a useful, narrower question than the prior static
forecast experiments: whether a nominated orbit's **short-horizon frequency increment** predicts
the displacement of the next detector candidate set after anchoring at the last observed nonempty
set. It does not test whether the prefix-fitted absolute CFO remains aligned, and a positive result
does not identify the satellite.

The experiment is suitable for a bounded calibration-only fit followed by frozen replay on the
existing pilot evaluation and explored DS8 panels. Its strongest evidence would be orbit increment
beating both zero- and reversed-increment controls on the identical windows with the same fitted
reception parameters. Static-prefix forecasts and the prior causal full-calibration result remain
contextual baselines because they use a different frequency construction.

## Conditional density and normalization

For lane alias period `P`, receiver `r`, hypothesis `h`, current time `t`, and last nonempty
candidate set `Y_r(t0) = {y_j}`, the historical branch should be exactly

```text
delta_h = wrap_P(mu_h(t) - mu_h(t0))
s(h_age) = sqrt(2 * 500^2 + (500 * h_age)^2) Hz
g_h,r(f | history) = 0.8 / |Y_r(t0)| * sum_j WN_P(f; y_j + delta_h, s)
                       + 0.2 / P.
```

`WN_P` must be a normalized wrapped-normal density, not a nearest-alias residual score. The equal
mixture over the previous candidates, the 0.8/0.2 mixture, and the uniform `1/P` term then each have
known mass and `g` integrates to one. In the no-history branch,

```text
g_h,r(f) = 0.8 * WN_P(f; mu_h(t), 500 Hz) + 0.2 / P
```

is also normalized. Apply wrapping after adding the orbital increment. The `500 * h_age` term has
units of Hz only if 500 is explicitly a frozen Hz/s drift-uncertainty coefficient and `h_age` is in
seconds; persist those units in the receipt.

The existing candidate-set kernel can use `g/f_causal` as its signal-assignment ratio while the
causal reference supplies the background set density. This remains a proper one-signal-plus-
background conditional density because `g` is normalized and depends only on the past. Compute the
ratio in log space or with a documented positive floor from the already normalized reference; do
not silently clip large ratios in a way that changes density mass.

## Required causal history contract

Maintain one history per exact lane and receiver. A window must be scored before any candidate in
that window is appended to history. RX0 may never seed RX1, and histories may not cross recording,
channel, edge or actual RF. A qualified empty set contributes its proper likelihood but does not
replace the last nonempty anchor. Missing or malformed receiver data is an exclusion under the
existing dataset contract, not an empty update.

When the last nonempty set is more than 10 seconds old, use the declared no-history branch. Do not
clamp age to 10 seconds, retain the old frequencies with a capped variance, or drop the current
window. Carry a qualifying reception history into held frequency without reset, since the proposed
endpoint is prequential transfer across that boundary. Initialize each lane independently.

For the historical branch, evaluate `mu_h(t0)` from the persisted forecast for the exact historical
source window. Do not interpolate from current outcomes or choose a historical candidate according
to its current residual. Every candidate in the last nonempty set receives equal mixture mass,
including alternatives that later look poor. The current set must not affect branch choice,
bandwidth, historical candidate weights, or the 10-second age decision.

An implementation audit should perturb current-window frequencies while holding the past fixed and
show that the current `g` is unchanged. It should also perturb future and held windows and show no
effect on earlier densities, verify independent RX histories, empty-set retention, exact 10-second
boundary behavior, role-boundary carry, candidate permutation invariance, alias-period shift
invariance, and numerical integration to one.

## What is identifiable

Anchoring at an observed past candidate cancels an unknown local absolute offset. The remaining
hypothesis-dependent quantity is

```text
mu_h(t) - mu_h(t0).
```

Therefore this model can identify only differences in short-horizon predicted slope/curvature among
nominated hypotheses. A shared increment across candidates improves local prediction but supplies
little identity information. Before interpreting candidate association, report the prior-weighted
between-hypothesis spread of `delta_h` per lane/window and the fraction of windows where the
differences are small relative to `s(h_age)`. Do not call a gain identity evidence when every
nominee induces essentially the same shift.

The empirical two-history causal reference estimates observed local velocity. The new `g` instead
uses one observed anchor and orbital displacement. Their comparison asks whether orbital increment
adds a useful signal component beyond the empirical background/reference. Shared use of past
observations does not make the comparison invalid, but it means a gain cannot be credited to
long-horizon TLE/CFO alignment. It is a short-memory conditional forecast.

The 20% uniform birth term also limits discrimination by design. Improvement may arise because the
model follows a generic monotone Doppler slope while the broad uniform term absorbs discontinuities.
Report signal/birth contribution diagnostics and candidate-increment spread rather than posterior
concentration alone.

## Controls and fair comparisons

Use identical histories, candidate sets, reference densities, visibility masks, bandwidths,
birth mass, occupancy dynamics, geometry coefficients and denominators for these frozen transforms:

1. **Orbital increment:** `y_j + mu_h(t) - mu_h(t0)`.
2. **Zero increment:** `y_j`, retaining the same age-dependent bandwidth.
3. **Reversed increment:** `y_j - (mu_h(t) - mu_h(t0))`.
4. **Quarter-period control:** apply the predeclared `P/4` shift only to the signal density, never
   to history, observations or the causal reference.

Score all transforms with the same calibration-fitted D/E/S/T parameters if the purpose is to
isolate the forecast transform. If each transform is refitted, give every transform the identical
two-start optimizer, priors and calibration population and state that the comparison includes
refitting. Do not fit the favorable control policy after evaluation signs are known.

Receiver swap and geometry reversal change only geometry covariates. They must leave `g`, its
history, the orbital increment and the causal reference byte-identical. Conversely, reversed Doppler
changes only `delta_h`; it must leave geometry and histories unchanged. These invariances separate
frequency and geometry effects.

The existing frozen causal full-calibration static-forecast model has fixed parameters and supplies
an honest deployment baseline. It is not nested with the newly fitted short-history model: the
short-history branch observes a recent candidate anchor that the static model does not use. Report
`orbit - static` as a transfer comparison, and use `orbit - zero` plus `orbit - reversed` for the
specific orbital-increment claim.

## Population, fitting, and reporting

Physically restrict fitting inputs to reception windows from the six calibration recordings before
constructing scalers, histories, references or optimization arrays. Calibration held windows, the
four pilot evaluation recordings and DS8 must not influence parameters or fixed hyperparameters.
The stated 500 Hz noise, 500 Hz/s drift uncertainty, 10-second maximum age and 0.8/0.2 mixture need
to be frozen before evaluation. If they were chosen from earlier outcome inspection, disclose that
development provenance.

Replay full reception then held sequences for the pilot evaluation and DS8, carrying histories
causally. The primary transfer endpoint should remain held log predictive density normalized within
record and averaged equally across records. Reception is a conditioning/diagnostic role, not a new
selection stage. Report the panels separately: pilot evaluation is reused evidence and DS8 is now
explored, so neither is a fresh confirmation.

Report, by panel, role and receiver:

- window totals, empty histories, historical branches, stale-history fallbacks and empty current
  sets;
- age distribution and density normalization checks;
- D/E/S/T relative to the same causal reference;
- orbit-minus-zero, orbit-minus-reversed, orbit-minus-static, receiver-swap, geometry-reversal and
  quarter-period contrasts with per-record signs;
- between-hypothesis increment spread relative to bandwidth; and
- posterior presence separately from conditional nominee entropy.

Do not select records or windows by observed alignment, proximity to a forecast, nonempty current
sets, control success or posterior identity. Qualified empty sets are essential missed-detection
evidence. A positive short-horizon result means that frozen orbital increments improve a causal
local candidate-set forecast under this mixture. It does not repair or validate the original
long-horizon absolute forecast, resolve aliases, prove a common emitter across receivers, establish
satellite identity, or support receiver direction/localization claims.

## Completed outcome and independent audit

The bounded fit and both frozen panel replays completed successfully. The independent
`audit_results.py` reconstruction is recorded in `audit-results.json` with status `pass`. It binds
the model, both result files and source datasets; reproduces the 1,356 calibration-reception window
IDs; and recomputes the relative evidence, Gaussian-prior penalty and MAP gain for both converged
starts of D/E/S/T. It also reconstructs every role total from exported per-window scores, checks all
equal-record aggregates and sign counts, verifies a common causal reference across every arm and
control, checks 285,720 strictly earlier causal-history links, and numerically integrates 200
exported target densities. The DS8 static-causal arm reproduces the previously sealed DS8 result
exactly for every record, arm, role and window export.

The short-horizon signal mechanism transfers strongly as a generic frequency predictor. Held T
beats the causal reference by 0.184294 nats/window on the pilot evaluation and 0.214494 on DS8,
positive on all four records in each panel. It beats the previously frozen static-causal T by
0.202054 and 0.219270 respectively, again 4/4. The orbital increment itself passes its direct
controls: T minus zero motion is +0.172402 pilot and +0.109660 DS8, while T minus reversed motion is
+0.193445 and +0.148429, all positive on all records. These results support the narrow claim that
the frozen orbital increment improves prediction after a recent observed-frequency anchor.

They do not support the receiver-tilt model. On the pilot panel T-D is -0.093277 (1/4 positive),
T-S is -0.116949 (0/4), and T-swap is -0.129924 (0/4). On DS8 T-D is -0.009269 (2/4), T-S is
+0.006355 (2/4), and T-swap is +0.031818 (3/4). The candidate-geometry permutation is better than
T on average in both panels: T-minus-permutation is -0.016492 pilot and -0.032229 DS8, with 2/4
positive in each. Geometry reversal is not a substitute for these failed nesting and permutation
checks.

The shared spatial arm is also inconsistent relative to D. Derived from the frozen per-record
contrasts, S-D is +0.023671 on the pilot panel (3/4) and -0.015623 on DS8 (2/4). Thus the positive
T-versus-reference result is driven by the new short-history frequency mechanism, not stable
incremental tilt or candidate-specific geometry. Both panels were previously explored. The result
should guide development of short-horizon association, but no geometry, identity, receiver-order or
localization model should be promoted from it.
