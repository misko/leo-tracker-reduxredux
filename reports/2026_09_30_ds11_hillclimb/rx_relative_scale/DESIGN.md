# DS11 independent-t4 RX relative-scale assessment

## Prior evidence and exact distinction

The proposed feature has already reached two later geographic-likelihood gates.
On pooled DS10 q=0.2 contrasts, scalar-derived variable weights lost held score
to both fixed-100 and a matched receiver-constant control. Direct donor
calibration of that contrast likelihood also transferred worse than its
receiver-constant control, so no second geographic fit was run. Those results
are in `2026_09_30_ds10_scale_weighting`, `2026_09_30_scale_score_diagnostic`,
and `2026_09_30_contrast_scale_calibration`.

The remaining distinction was the original independent Student-t4 track
mixture used by DS11 single scans. `diagnostic.json` evaluates that exact
likelihood at every original IID endpoint. It performs no location or timing
fit. Features and scale assignments use training observations only; held
observations enter only the frozen-point transfer score.

## Frozen coefficients and pairing rule

The donor DS7--DS9 individual-channel calibration is:

```text
RX0: log(scale) = 3.5107092418 + 0.3281986404 log(feature)
     constant log(scale) = 5.0059645041
RX1: log(scale) = 3.1692042643 + 0.3941635314 log(feature)
     constant log(scale) = 4.9748356824
```

Only the relative ratio `exp(variable log scale - donor constant log scale)`
would be applied, keeping the original 100 Hz scale as the anchor.

Within each scan, assign a physical NORAD to a track only when its largest
original-IID training candidate probability is at least 0.5. This is the
closest independent-IID counterpart of the donor rule, which required q=0.2
candidate mass times signal responsibility of at least 0.5. Pair RX0 and RX1
tracks with the same physical NORAD and exact RF. Pair observations by mutual
nearest timestamps within one microsecond. Require at least eight both-training
pairs spanning at least five seconds. Define

```text
feature = max(1 Hz, 1.4826 * MAD(centered training RX0-RX1 residual difference)).
```

If a track participates in multiple accepted pairs, use its median log
feature. Unsupported tracks retain ratio one. The matched control uses the
within-scan median log ratio separately for RX0 and RX1 on exactly the same
supported tracks; this preserves each scan's typical receiver scale while
removing track-level variation. It uses no held value or geographic reference.

All observations and candidate mixtures remain. A direct implementation would
profile each track/candidate CFO independently at `sigma = 100 * ratio` and use
the normalized t4 density, including `-log(sigma)` per observation. The CFO
prior remains in physical Hz. It would expose exactly two arms:
`track_variable` and `receiver_constant`.

## DS11 coverage and fixed-point gate

All 32 scans have feature coverage. Among 1,923 tracks, 1,917 pass the 0.5 IID
candidate rule. Of 611 possible matched cross-RX track pairs, 495 pass the
training support rule; all 495 also happen to have at least three paired held
observations, matching the original calibration population. They support 989
tracks (51.43%). Each scan has 10--20 accepted pairs and 20--40 supported
tracks. Predicted physical scales range from 51.18 to 150.56 Hz.

At the frozen IID endpoints, track-variable beats the matched receiver-constant
control on 20/32 scans, with +74.074 total held log units and +4.195 median
scan gain. It does not beat the actual fixed-100 baseline: variable wins only
13/32, totals **-560.657** held log units, and has a -2.390 median scan gain.
The matched constant control is worse still at -634.731 total and 12/32 wins.

The screen-8 slice gives the same decision. Variable beats the matched control
on 7/8, but beats fixed-100 on only 4/8 and totals -263.104 held log units.
The remaining 24 scans were also already evaluated by this fixed-point audit:
variable beats fixed-100 on 9/24 and totals -297.554.

This is adequate coverage but adverse same-likelihood transfer. The arm should
close before geographic fitting. Its relative advantage over an even worse
matched control does not overcome its large loss to the current likelihood.

## Leakage and interpretation risks

- Candidate identity and the feature are conditioned on the same scan's fitted
  IID training endpoint, so this is empirical-Bayes weighting.
- Donor coefficients came from q=0.2 geography-conditioned residuals; the IID
  0.5 candidate rule is analogous but not the same population.
- Alternative track pairs can reuse observations. Pair and held-score totals
  are dependent, not independent trials.
- A receiver difference cancels common error. The individual-channel transfer
  showed some shared predictive content but did not establish causal sensor
  variance or absolute uncertainty.
- Physical identities depend on the digest-bound archived catalogue mapping.
  Candidate slots must never substitute for NORAD.
- Held values and the reference position must remain absent from feature,
  support, coefficient, and control construction. The fixed-point held result
  above is an exposed diagnostic used only to stop the route.

If this model were ever revisited with new independent donor evidence, required
tests would cover exact ratio-one IID parity, normalized t4 density and
gradient, independent CFO profiling, physical-ID slot permutation, mutual
nearest pairing, held/reference mutation invariance of all weights, unsupported
fallback, full observation accounting, and source/hash bindings.
