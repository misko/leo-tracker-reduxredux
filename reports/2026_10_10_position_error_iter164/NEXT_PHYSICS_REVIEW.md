# One remaining physical lever: measurement information per window

Source/report review only. No recordings, reference documents, new outcomes or
closed reserves were accessed. This is a proposal, not an experiment approval.

The most defensible next typical-error hypothesis is **heterogeneous CFO
measurement precision**, rather than another position search or clock repair.
Current B7 gives every admitted frequency window the same Gaussian width.
The known-pilot estimator integrates unequal signal amplitudes and support;
its information about CFO can differ substantially between windows. Equal
weight can let weak or distorted measurements dominate a geometric direction
that is already strongly confounded with receiver clock and satellite timing.
An information-aware likelihood might improve typical accuracy; it cannot
remove a common physical bias or create missing geometric information.

## Concrete mathematical lever

For an independently characterized complex pilot workspace with mean
`A*s(t)*exp(i*(phase + 2*pi*f*t))` and complex noise variance `nu`, profiling
unknown constant phase leaves local CFO information proportional to

`I_f = (2/nu)*(2*pi)^2 * sum(|A*s(t)|^2*(t-t_weighted)^2)`.

This expression requires the actual estimator's admitted/interpolated support
and noise convention. It is not justified by a GLRT margin or arithmetic
duration alone. If amplitude, interference or acquired CFO are additional
estimated nuisances, use their Schur-projected information, not the unprofiled
curvature. A negative/ambiguous profile curvature is unavailable information,
not a license to assign infinite confidence.

The lean first candidate is conservative downweighting only:
`sigma_i^2 = max(125^2, 1/I_f_i)` in Hz squared. Keep the existing 125 Hz
baseline floor globally, unchanged observations and full normalized mixture
event/clutter factors. Both c arms receive the identical acquisition-derived
widths. This is one exploratory hypothesis, not a claim that 125 Hz is a
calibrated independent model-noise variance. It cannot sharpen apparently good
windows beyond deployed precision and does not choose a width from position
error. Unsupported windows keep the ordinary 125 Hz width and are counted.
Report how many widths actually change before interpreting any result.

## Availability and a cheap falsification gate

The existing on-disk IQ and public visit/window identities supply the necessary
acquisitions; earlier replays covered the same 35,206 pilot observations.
However, persisted TrackingCandidate metadata do not retain the complex
symbol correlations, noise variance or per-frame curvature. This is a real
availability gap, documented in [153's review](../2026_10_10_position_error_iter153/REVIEW.md).
No metadata-only reconstruction of exact information is possible.

Before localization fits, a separately frozen bounded replay of existing IQ
must establish the exact native backend/build/template/support convention and
measure acquisition-only information. Synthetic noise and chirp tests should
check estimator calibration and support parity. Do not fabricate precision
from margin. Stop if the public estimator workspace cannot be reconstructed,
if information is poorly calibrated under the inspected signal model, or if
almost no windows exceed the baseline floor. Those outcomes would falsify this
particular useful-information hypothesis without spending on position fits.

If that gate passes, freeze one matched twelve-member comparison: fresh ordinary
control versus this single global width rule, both c arms, same ordinary starts,
banks, priors and optimizer budgets. Include every observation and unavailable
precision count; preserve failures and all paired regressions. Seal before
reference evaluation. Report frequency likelihood, support/responsibility
changes, qualification, per-dataset typical/tail errors and runtime separately.
No width sweep, per-scan winner, new RF or reserve access is needed.

## Why this is distinct from the previous work

- [121 fusion](../2026_10_09_position_error_iter121/RESULTS.md) reduced a
  conditional stationary update metric but retained displacement; it did not
  improve standalone measurements.
- [144 catalogue sensitivity](../2026_10_10_position_error_iter144/DECISION.md)
  put 99.9272–99.99998% of prediction changes in the unconstrained nuisance
  span, providing no calibrated alternative orbit covariance.
- [145 paired correlation](../2026_10_10_position_error_iter145/DECISION.md)
  improved fitted-c mean only 3.31 m and worsened c=0 by 42.30 m. This proposal
  changes individual acquisition precision, not correlation or shared labels.
- [153 CFO timing](../2026_10_10_position_error_iter153/REVIEW.md) identified
  missing actual estimator weights; this proposal measures them rather than
  applying an unsupported timestamp correction.
- 161–163 tested full-data-conditioned splits and training minima. Their small
  selection gains do not establish that uniform measurement precision is
  physically appropriate. Active 164 addresses discovery/tails; this lever
  addresses measurement weighting around ordinary geometry.

The principal risk is that current error reflects clock/orbit bias rather than
CFO measurement noise. Then even correctly estimated precision will not help,
and downweighting will merely discard spatial information. A qualified minimum
does not resolve that distinction. The proposed replay gate and one fixed
matched pilot can reject the hypothesis honestly; no benefit toward 0.4 km is
claimed now.
