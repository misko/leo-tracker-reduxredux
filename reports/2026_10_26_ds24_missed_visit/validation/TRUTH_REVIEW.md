# Synthetic truth and scorer convention review

Reviewed before numerical outcomes, 2026-10-26 21:44 UTC. Source snapshots:
`timing/timing_search.py` SHA256
69fa2e2b10a2bd63f79ee955af13468f9806644a057ac2c1e94d616a8485b89b,
and the newly frozen `timing/study.py`/protocol receipt.

The generated target carrier has phase
`2*pi*((213456.75 + true_rate*.354)*t + .5*true_rate*t*t)`.
Its instantaneous CFO at the common20ms-window midpoint t=.010s is therefore
exactly `213456.75 + true_rate*(.354+.010)`, the evaluation value. The correctly
propagated packet uses that same midpoint plus the declared donor error. The
fallback deliberately omits evolution. There is no start-versus-midpoint20Hz
comparison error in the returned target CFO evaluation.

Timing is generated independently by replacing local clock time with
`t*(1-timing_rate/sample_rate)` before frame/symbol assignment. To first order,
the nominal-frame epoch at t=.010s is `4321.25 + timing_rate*.010`: ±1sample
for the±100samples/s truth. The evaluation uses exactly that convention. The
rate-propagated packet advances its epoch by the same amount, while the
zero-rate packet deliberately does not. The exact simulated clock also changes
symbol/frame spacing; a constant midpoint epoch is an approximation, explicitly
reported by the scorer. Tests do not assume that simulated clock drift only
changes a scalar phase while leaving symbol spacing fixed.

The scorer removes the earlier predicted instantaneous CFO separately at each
pilot frame's mean sample time, profiles each frame's complex phase independently
through its power statistic, then returns the residual FFT bin at the common
target-midpoint reference. A per-frame constant frequency differs from exact
chirp integration only by a frame-local quadratic term; arbitrary frame phase
is discarded. This approximation is far below a frequency bin for the stated
±2000Hz/s controls and is not a donor-posterior shrinkage step.

One metadata caveat remains: the fabricated earlier donor has support[0,200000)
and scalar CFO213456.75+error, but no explicit earlier CFO reference counter.
The harness currently defines213456.75as the carrier evolution intercept before
adding0.354s, not as a separately generated earlier-window midpoint measurement.
Thus its target errors are internally consistent, while an interpretation as
two physically generated windows with donor CFO at its midpoint would need an
explicit10ms reference adjustment. Label the synthetic earlier-CFO origin or
add its reference counter; do not claim it validates natural measured-donor
reference accuracy. This caveat does not change the current target truth or
the known-target accuracy comparison.

The full-support/public-scorer parity tests and actual synthetic outcomes still
need independent review. Mathematical convention review alone does not certify
the strong/null screen or authorize a position run. No held-validation targets,
IQ outcomes, GPS or geographic errors were opened in this review.
