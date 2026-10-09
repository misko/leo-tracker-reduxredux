# Partial visibility does not directly specify GLRT detection probability

Source audit plus bounded synthetic native calls, 2026-10-09. No recordings,
receiver reference coordinates, orbital predictions, positioning objectives,
RF collection or deployment were used. This is not a calibrated detection law.

The actual conditioned estimator normalizes away much of the loss of signal
support in a noiseless coherent burst. Therefore the finite-support occupancy
construction in [118](../2026_10_09_position_error_iter118/INTEGRATION_SUPPORT.md)
supplies a geometric time scale, but does **not** by itself justify `p=q*v`.

## Source contract and exact statistic

The [native GLRT](../../src/leo/analysis/native_presence/presence.c#L608)
derotates at the acquired CFO and correlates each of 64 known symbols against
the exact and rolled-control templates. Integer sampling and fractional
16-tap normalized Lanczos interpolation have distinct support guards. Up to
16 supporting frames contribute; a complete 20 ms synthetic probe here has
15. Frame phases need not remain coherent: power is summed across frames,
whereas symbol correlations are coherently combined within each frame.

For exact or control correlations `z_fs`, the implemented statistic is

```
S = max_b [sum_f |sum_s z_fs exp(-2*pi*i*b*s/512)|^2]
          / [sum_f (sum_s |z_fs|)^2].
```

The 128-point autocorrelation transform followed by 512-point evaluation is
an execution detail, not 512 independent observations. Exact and control use
their **own** denominator and maximizer. Zero denominator returns score zero.
The exact maximizing bin supplies residual CFO
`signed_bin / (512 * 4.4e-6)` (about 443.9 Hz per bin); acquired CFO is added
afterward. Consequently a stable exact-bin result in this synthetic example
does not establish sub-bin accuracy, a CFO variance, or actual acquisition
success. See [native accumulation and normalization](../../src/leo/analysis/native_presence/presence.c#L690)
and the independent [Python autocorrelation implementation](../../src/leo/analysis/starlink/pilot_methods.py#L1256).

The native [fractional confirmation](../../src/leo/analysis/native_presence/presence.c#L888)
first checks a five-cell integer epoch surface, requires a bracketed
negative-curvature log peak, then recomputes scores and CFO at the fractional
offset. The Python scanner route likewise [refines epochs](../../src/leo/analysis/starlink/pilot_methods.py#L500),
although its lattice execution/support policy is not asserted identical to
every native acquisition build. This audit tests the shared **conditioned
scorer**, not the full blind proposal/epoch pipeline or a deployed binary.

The adaptive analysis publishes
[`passed_fractional_margin_gate`](../../src/leo/scanner/adaptive_hop_analysis.py#L533)
from `exact-control >= configuration.glrt64_margin_gate`, whose current
[default is 0.025](../../src/leo/scanner/adaptive_hop_analysis.py#L57).
[Position projection discards failing candidates](../../src/leo/application/scanner_trajectory.py#L61).
Other native decision routes additionally use an exact-score floor of .175;
that separate [host decision](../../src/leo/analysis/native_presence/host_decision.c#L111)
must not silently replace the adaptive positioning admission contract.
Acquisition retention, fractional completeness, margin admission and winner
selection all condition the population of CFO measurements.

## Bounded native synthetic result

[partial_signal.py](partial_signal.py) generates one 20 ms, 2.5 MS/s lower-edge
pilot at known synthetic epoch/CFO zero. A single physical turn-off removes
the transmitted signal after the chosen time; receiver noise, when present,
continues through the full probe. No samples are trimmed from the estimator.
The diagnostic supplies the epoch/CFO to isolate conditional estimation.

[Five tests](test_partial_signal.py) passed in **2.47 s**, including compilation,
under production Python with BLAS/OMP/MKL threads fixed to one. Four cutoff
cases (0.15, 1, 5 and 20 ms) use the actual native `leo_presence_glrt` API and
the public Python conditioned scorer as a numerical oracle. Both scores agree
to absolute `1e-10`. All four noiseless exact scores equal one within `1e-10`,
with zero residual CFO. Multiplying the complete input by .01 preserves all
three returned values within `1e-10`. A fifth noise-only case retains all
50,000 noise samples when signal occupancy is zero and returns a finite,
nonzero coherence score below one. No Monte Carlo detection probabilities
are estimated by these five tests.

| Signal turn-off | Approximate pilot-sample occupancy | Native noiseless exact score |
|---|---:|---:|
| 0.15 ms, within first burst | 3.34% | 1 |
| 1 ms, after first burst | 6.67% | 1 |
| 5 ms, after fourth burst | 26.67% | 1 |
| 20 ms, complete probe | 100% | 1 |

This follows analytically: after perfect CFO removal, nonnegative real exact
symbol correlations attain their coherent ceiling at bin zero even when many
symbols/frames are absent. Amplitude scales numerator and denominator equally.
Thus score is not an occupancy estimator. This counterexample **does not**
prove that detection probability is independent of occupancy in noise: absent
signal intervals still contribute noisy correlations to both numerator and
denominator. Neither an exact score of one nor known conditional CFO proves
that the full scanner would acquire and retain the candidate.

## Small next measurement experiment, not a frozen trial

Before choosing any geometric soft likelihood, run a predeclared synthetic
screen with the same actual conditioned native estimator: fixed receiver-noise
law, fixed received amplitude while on, one monotone turn-on/turn-off through
the known pilot support, and independent noise seeds. For example, 5 cutoff
fractions × 2 independently specified signal/noise levels × 16 seeds = 160
conditioned calls. Include a noise-only row set and full-support reference;
do not renormalize total signal energy across occupancy. Report exact/control
scores, margin-pass fraction with its binomial uncertainty, CFO residual-bin
distribution and support geometry. Reverse turn-on/off orientation at the
same occupancy in a separately budgeted sensitivity to test whether occupancy
alone loses relevant temporal arrangement. Record call time before expanding.

The falsifiable question is whether `P(margin pass | occupancy, amplitude,
noise, correct acquired seed)` is approximately `v` times its full-support
value over the fixed settings. If not, reject the linear law, rather than tune
an angular width against position error. Even agreement would only support a
conditional approximation: subsequently measure blind acquisition, bracketed
fractional refinement, candidate competition and admission with fixed settings
before interpreting the result as the operational `p` in a satellite mixture.
Fixed seed in this diagnostic is synthetic signal configuration, not a
ground-truth-assisted operational position or satellite selection.

An operationally useful probability also needs signal/noise conditions not
currently encoded as a calibrated per-window uncertainty. The source audit
in [111](../2026_10_09_position_error_iter111/MEASUREMENT_INPUT_AUDIT.md)
documents that omission. A synthetic AWGN experiment alone cannot validate
real multipath, fading, occultation transition physics or clutter calibration.
Keep the existing hard likelihood unchanged until the measurement law and
its assumptions have independent evidence; no new smoothing parameter is
recommended by this audit.
