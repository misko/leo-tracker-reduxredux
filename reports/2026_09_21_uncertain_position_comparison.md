# Position refinement with identity and orbital uncertainty

The archived replay now implements separate comparisons for satellite-identity
ambiguity, observation clustering, and strictly causal orbital prediction error.
The strongest result is an **exploratory approximately 275 m horizontal
error**, compared with **4,859 m** for the matched fixed-UTC baseline. Its
randomized held-out Doppler RMS falls from **157.09 to 78.63 Hz**. This is a
single-site archived result, not a calibrated 275 m accuracy guarantee or a
production deployment.

## The change that produces the largest gain

Learn a phase-error prior from catalogue updates collected before the first
target capture. Use that prior to constrain one orbital phase-rate correction
per candidate satellite, shared across its retained observations. Jointly fit
those corrections and receiver position using fitting RF observations only.
At a capture, the correction is the learned mean plus a fitted rate correction
times the causal TLE's epoch age. Later TLEs and the reference receiver coordinate
do not fit these parameters.

This model acknowledges that fixing each archived TLE as exact can bias receiver
position. It also introduces substantial flexibility: the all-satellite variant
fits 446 satellite correction parameters plus two receiver-position parameters,
alongside profiled source frequency offsets. Satellite identities remain fixed
in this experiment. It must not be described as the completed joint
identity-and-orbit mixture model.

| Matched fixed-UTC experiment | Horizontal error | Randomized held-out RMS |
|---|---:|---:|
| Existing strict causal fit | 4,859 m | 157.09 Hz |
| Frozen causal orbital correction, no RF adjustment | 3,787 m | 155.04 Hz |
| RF adjustment for repeatedly observed satellites only | 2,443 m | 122.08 Hz |
| RF adjustment for all retained candidate satellites | approximately 275 m | 78.63 Hz |

Exact SGP4 propagation checks the approximation used by the joint fit. The
all-satellite result is sensitive to data selection: four predefined NORAD-group
deletions produce errors from **28 m to 1,015 m**; four recording-group deletions
produce **473–917 m**. Halving or doubling prior width gives approximately
**498 m and 222 m**, respectively. Those are sensitivity checks, not independent
sites or additional parameter settings chosen for deployment. One correction
reaches its allowed rate bound.

![Orbital uncertainty experiment and sensitivity checks](2026_09_21_causal_orbit_error_model/uncertainty.png)

The [orbital-model report](2026_09_21_causal_orbit_error_model.md) documents the
prior, exact numerical verification, all variants, and limitations. Residual
holdout remains randomized within observed arcs; the resulting validation does
not independently establish correct satellite identities or orbit estimates.

## Observation weighting and uncertainty

The [weighting comparison](2026_09_21_position_weighting_uncertainty.md) preserves
the shared bounded-clock baseline. Equal candidate-pass weighting reduces error
from **4,503 to 4,289 m**; combining it with the frozen causal orbital prior
reaches **3,616 m**. It also reduces worst group-deletion shifts compared with
observation weighting. These shared-clock numbers must not be substituted for
the fixed-clock baselines in the orbital-uncertainty table above.

Cluster-aware local uncertainty is larger than the IID calculation, but remains
much smaller than the multi-kilometre actual errors in these simpler models.
It does not account for all common orbital biases. A small local covariance is
not evidence of a correct absolute location.

## Retaining satellite identity uncertainty

The new numerical mixture keeps competing catalogue identities and an unassigned
component, profiles source frequency offsets on fitting observations only, and
conditions randomized held-out prediction on those fitting weights. It preserves
full-catalogue prior mass instead of renormalizing a convenient shortlist. All
four fixed-clock starts reach the same local mode. Three shared-clock starts
reach the leading mode; the fourth remains in a worse basin. Selection uses
fitting evidence only, and the report preserves the alternative basin.

| Same 622 episodes and strict causal catalogue | Horizontal error | Randomized held-out RMS |
|---|---:|---:|
| Fixed identities, fixed UTC | 4,859 m | 157.09 Hz |
| Identity mixture, fixed UTC | 4,867 m | 159.60 Hz |
| Fixed identities, bounded shared clock | 4,503 m | 156.22 Hz |
| Identity mixture, bounded shared clock | 4,504 m | 158.71 Hz |

This is a negative result for identity uncertainty alone on this cohort. The
mixture RMS is a fitting-posterior-weighted residual metric, not a reselected
held-out winner. The full-catalogue check at each reported mode finds maximum
omitted signal fractions below 8e-12. That verifies the local shortlist, not a
global search over Earth. Likelihood scales, visibility, and the full-catalogue
prior remain modelling assumptions; posterior weights are not calibrated
identity probabilities.

See the [identity-mixture report](2026_09_21_identity_mixture_positioning.md)
for candidate support, optimization starts, provenance, and complete results.

The fully combined identity-and-orbit model remains unfinished. In particular,
applying an orbital correction only to the old winner would unfairly privilege
that identity. We rejected that shortcut rather than claiming it implemented
the combined model. A valid integration must apply the orbital uncertainty model
to every competing identity and repeat the catalogue-tail checks after fitting.
The covariance work is likewise a weighting and uncertainty diagnostic, not yet
a complete correlated-noise generative likelihood.

## Recovering excluded RF support

The previous research export kept the longest qualifying track per channel/edge
from the leading RF hypothesis, with a 14-observation / 7-second eligibility cut.
The new read-only exporter retains every non-overlapping tracklet in that same
RF hypothesis, preserving reconstruction's existing detection gates. It does
not promote arbitrary raw peaks into satellite tracks.

| Same 211 recordings | Previous export | Expanded export |
|---|---:|---:|
| RF tracklets | 684 | 1,774 |
| Unique observations | 24,149 | 43,831 |
| Tracklets below the previous eligibility cut | 0 | 553 |

All 211 capture and analysis digests matched the frozen source records. No
original exported observation was lost and the exporter rejects duplicate
observation IDs. The extra 1,090 tracklets include **537 additional tracks above
the old cut**, as well as the 553 shorter/sparser fragments. Thus longest-per-lane
selection was excluding useful-looking longer support too.

Recovery alone does not prove improved positioning. The matched 622-episode
model comparisons above deliberately retain their original 21,702 observations.
The remaining 62 episodes in the previous export were not in that positioning
cohort. Expanding support changes the inference problem and must be separately
evaluated, including uncertain and unassigned associations.

The [expanded-support experiment](2026_09_21_extended_tracklet_positioning.md)
now tests four nested cohorts with fresh fitting-only associations. It uses the
frozen per-session operational catalogue, still strictly pre-capture, rather
than the freshest-across-archive composite. Its matched baseline is therefore
reported separately; eight of 622 baseline identities change under that policy.

| Support under the extension's matched catalogue policy | Tracks / observations | Observation-weighted position error | Held-out RMS |
|---|---:|---:|---:|
| Original positioning cohort | 622 / 21,702 | 4,481 m | 165.93 Hz |
| All previously exported tracks | 684 / 24,149 | 4,582 m | 310.26 Hz |
| All reconstructed tracks meeting the old cut | 1,221 / 38,057 | 3,901 m | 307.02 Hz |
| Include the 553 shorter/sparser fragments too | 1,774 / 43,831 | 3,930 m | 294.20 Hz |

Additional gate-length tracks improve position in this conditional experiment.
Adding the short fragments then lowers RMS but worsens position by 29 m with
observation weights, or 93 m with pass weights. This is a negative result for
unconditionally admitting the short tracks with hard identities. It does not
establish that those fragments are useless in an uncertainty-aware joint model.
It also demonstrates why lower aggregate RMS alone is not our acceptance test.

- [Per-recording recovery audit](2026_09_21_uncertain_position_comparison/support-recovery.json)
- [Expanded evidence digests](2026_09_21_uncertain_position_comparison/support-evidence-digests.json)
- Exporter: `tools/export_position_tracklets.py`

## Scope and interpretation

These are research scripts over archived data. They do not change recording
configuration, production association gates, or the scanner queue. No new RF
collection was used. The [comparison protocol](2026_09_21_uncertain_position_protocol.md)
separates accuracy, predictive residuals, stability, and uncertainty calibration.
Models and sensitivity variants are retained even where they do not improve
position. The known location is used only after each inference output is sealed;
the archive is nevertheless a previously studied single site, so independent
site validation remains necessary before a general accuracy claim.
