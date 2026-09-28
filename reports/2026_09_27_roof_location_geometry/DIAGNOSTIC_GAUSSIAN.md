# Fixed-100 Hz Gaussian diagnostic

This diagnostic uses only the completed Sacramento search artifact for
`scan-fw-00ff81dc09fc738a` and the already frozen six-scan calibration summary.
It does not inspect location truth, tune a geometry coefficient, or run another
location.

## Finding

The fixed 100 Hz Gaussian Doppler likelihood is not an adequate residual model
for this search.  At the point selected by both `D` and `D_plus_geometry`, the
occupied-second-weighted Doppler score is 37.9068 nats per reserved sample while
the complete reception contribution is 1.4812 nats.  This is not evidence that
reception geometry is intrinsically too weak.  Quadratic Gaussian tail loss is
dominating the natural joint likelihood because the residual distribution is
far wider and heavier-tailed than 100 Hz.

The 62 selected tracks have these MAP residual RMS distributions:

| RMS (Hz) | p10 | p25 | median | p75 | p90 | maximum |
|---|---:|---:|---:|---:|---:|---:|
| Doppler training | 92.0 | 156.4 | 399.2 | 763.0 | 1349.2 | 4213.6 |
| Doppler reserve | 107.3 | 177.8 | 408.3 | 737.8 | 1271.3 | 2974.7 |

The median reserve/training RMS ratio is 1.021 (p10 0.743, p90 1.481), so the
large reserve errors are not primarily a reserve-only collapse.  They are
already visible in training residuals.

Loss is highly concentrated.  A 19-second track with 2974.7 Hz reserve RMS has
mean Doppler NLL 447.98.  It has only 1.38% of occupied-second weight but
contributes 16.32% of the total Doppler objective.  The top 3, 5, and 10 loss
contributors supply 32.93%, 42.63%, and 63.30% of total Doppler loss while
carrying only 7.49%, 12.72%, and 21.73% of occupied-second weight.

The shortlist is also effectively discrete: 53/62 tracks (85.5%) have a stored
top weight exactly 1.0, and 60/62 (96.8%) have top weight at least 0.95.  Thus
the nominal top-three Gaussian mixture supplies little association uncertainty
for most tracks.  This follows directly from applying squared-error differences
at a 100 Hz scale; it is not a numerical-underflow error because normalized log
weights are retained.

The mismatch was predictable without this test search.  At the known roof site,
the six frozen calibration scans had MAP RMS p10/median/p90 approximately
57/156/474 Hz.  Even there, 100 Hz is below the median and dramatically below
the upper tail.  A single homoscedastic 100 Hz Gaussian therefore lacked
calibration support before geographic scoring.

## Next bounded iteration

Replace the frequency component with a fully normalized Student-t likelihood,
without residual clipping or an outcome-tuned multiplier.  Estimate its scale
and degrees of freedom exclusively from the six calibration scans:

1. At the known calibration roof coordinate, perform candidate selection using
   each track's Doppler-training observations only.  Profile a robust constant
   CFO per candidate (the Student-t location MLE, or a fixed median if a simpler
   predeclared implementation is desired).
2. Use held-out Doppler observations from calibration tracks to fit one frozen
   Student-t scale and degrees of freedom by total log likelihood.  Prefer
   leave-one-calibration-scan-out predictions when estimating these two
   parameters so the residual distribution is not evaluated on the same scan
   that determines it.  Do not use any location-test scan or its GPS truth.
3. In each geographic search, rank candidates and compute top-three prior
   weights from the robust training likelihood only.  Score reserve samples by
   the normalized top-three Student-t mixture, retaining its full log-density
   constants.  Keep candidate propagation and reception evidence out of the
   shortlist decision exactly as in the current protocol.
4. Add the frozen detection and conditional-ratio log losses with coefficient
   one.  This remains an uncapped natural composite: `D_t + detection +
   conditional_ratio`.  Preserve `D_t` and `D_t + detection` as ablations.
5. Freeze the likelihood family, scale, degrees of freedom, top-k, and search
   budget before rerunning any test location.  Judge success only by the
   separately computed kilometer error, not by selecting whichever likelihood
   or coefficient happens to favor test GPS.

A Student-t model is preferable here to an arbitrary loss cap: it assigns a
proper normalized probability density, retains all residual information, and
lets the calibration corpus determine the tail/geometry balance in natural
log-likelihood units.  If calibration cannot identify degrees of freedom
stably, freeze a small prespecified grid and choose it by calibration-scan
held-out NLL only; report sensitivity across that grid before test scoring.

This diagnosis does not show that robust Doppler plus reception will improve
location.  It shows that the current equality of the `D` and
`D_plus_geometry` selected point is not a clean test of that question because
the Doppler term is severely scale- and tail-misspecified.
