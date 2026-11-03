# Deployed-wrapper FFT feasibility

This is a bounded source and operation-count review. It does not change the
detector, run hardware, or claim a runtime improvement. The workload is the
2.5 MS/s, 120 ms DS9 wrapper: 3,333 epochs, 11 samples per anchor, 16 frames,
12 coarse CFO cells, 12 normal anchors, and 22 peer-fallback anchors.

## Exact full-grid convolution

The coarse dot product is a linear correlation. Reversing and conjugating each
rotated anchor/CFO template therefore gives a mathematically equivalent FFT
convolution. The exact index is the overlap-save output at `taps - 1 + epoch`,
offset by the current rounded anchor and frame starts. Received energy remains
the existing prefix-sum calculation, and support and anchor accumulation must
remain in their current order.

For one receiver, the normal scalar path evaluates 84,471,552 complex MACs:

```text
12 anchors * 16 frames * 3,333 epochs * 12 CFOs * 11 taps
```

The 22-anchor fallback evaluates 154,864,512 complex MACs. A normal dual-RX
call evaluates 168,943,104; a call that first evaluates both receivers and then
reruns one peer with 22 anchors evaluates 323,807,616.

The prior maintained overlap-save design uses a 64-point FFT and 54 useful
outputs for an 11-tap filter. Applied without dropping any wrapper hypothesis,
one normal receiver needs 11,904 shared input transforms and 142,848 inverse
transforms. Using the archived radix-2 model (`5 B log2(B)` real operations per
transform and `6 B` per spectrum product), this is 351,977,472 real operations,
versus 675,772,416 for the direct complex-MAC model: only a 1.92x operation
reduction before energy, magnitude, scatter, and call overhead. The ratio is
the same for 22 anchors. The archived ARM FP32 bank was already slower than its
direct FP32 baseline at this 11-tap rate (0.8254x), so a complete FP64 FFT bank
is not the lowest-risk route to the roughly 86x reduction still required.

A long transform does not improve the count. A 4,096-point transform covers a
frame's 3,333 epochs, but one forward plus 12 inverse transforms has essentially
the same operation count as direct correlation. Sharing one transform across
all anchor offsets requires a longer input region and 144 inverse transforms;
the additional outputs are unused and make the count worse. A whole-dwell
transform similarly computes far more correlation positions than the wrapper
reads.

FFTW plans, work buffers, and kernel spectra can be context-owned and reused
between calls. Cache keys must include rate, exact-template identity, receiver
center, residual bounds/grid, anchor schedule, and FFT length. Normal and
fallback schedules share only anchors 2 and 184; otherwise their kernel banks
differ. Input transforms cannot be shared between receivers. Receiver kernel
spectra can be shared only when the two centers and all other cache-key fields
are equal. The existing `leo_fft` wrapper exposes a context-owned FP64 forward
transform but no inverse/bank interface; the existing coarse bank is an
archived FP32 experiment, so neither is a drop-in exact implementation.

FFT arithmetic also changes reduction order. It can be numerically close to
the server scalar result, but cannot promise the frozen direct-rank and 1e-10
score gates by construction. An exact-result mode would still need a bounded
screen plus direct repair or a proved error interval and full direct fallback.

## Conditioned FFT path

The maintained conditioned CZT is a mathematically equivalent 100 Hz grid
evaluation, but its implementation is FP32, uses a process-global cache, and
relies on guarded FP64 rechecks. It is not the wrapper's current exact FP64
path. A context-owned FP64 CZT with a 4,096-point convolution could evaluate 41
bins for a 3,333-sample frame. The same operation model gives about 536,094
real operations per frame, versus 1,093,224 for 41 direct complex dots, a 2.04x
reduction. At eight candidates, 16 frames, and two receivers, that is about
137.2 million modeled operations instead of 279.9 million. The earlier FP32
CZT reduced measured conditioned time by 1.33x, so the operation ratio must not
be read as an ARM runtime prediction.

An exact-result conditioned experiment is feasible: use a context-owned FP64
CZT as a screen, compute a defensible transform-error interval, directly
recompute every bin whose upper bound can beat the best repaired lower bound,
and select only from exact repaired scores. It targets the remaining roughly
2.5 seconds per representative call, so even an ideal 2x result would leave the
wrapper tens of times beyond a 120 ms arrival interval.

## Recommended next experiment

The lowest-risk high-leverage experiment is a full-geometry FP32 interval
screen followed by certified FP64 direct repair, rather than full-grid FFT
convolution. The maintained FP32/NEON coarse kernel already evaluates the same
normal 12-anchor/16-frame geometry efficiently. It needs an isolated wrapper
variant for the twelfth bounded CFO cell, receiver center, and 22-anchor peer
schedule.

For every approximate grid cell, carry a conservative absolute error interval
covering template FP32 conversion and the 11-product FP32 accumulation. CI16
samples divided by 32,768 are exactly representable in binary32; rotated
template conversion error is known at setup. Use exact denominator arithmetic
for the screen so the interval does not depend on the NEON reciprocal-square-
root approximation. A cell can be discarded as a possible exact local maximum
only when its upper bound is below a neighbor's lower bound. Directly recompute
every remaining possible maximum and its epoch neighbors, then apply the frozen
stable rank and separation rules to exact scores. If any interval, allocation,
or frontier condition is unresolved, run the full scalar grid and expose that
fallback in telemetry.

The leverage comes from exact-work reduction. Repairing 64 provisional peaks
and both epoch neighbors costs 405,504 complex MACs for the normal schedule,
208x fewer FP64 MACs than its 84,471,552-MAC full-grid work. Repairing only the final
eight plus neighbors would be 1,666x smaller, but 64 is the appropriate first
bounded frontier experiment; the interval, not a fixed top-K assumption, must
decide whether it is sufficient. The FP32 full-grid screen remains additional
work and no runtime gain is claimed from these counts.

Acceptance should be: exact non-timing equality with the scalar wrapper on all
80 host cases; zero rank/status/epoch/gate/tolerance failures against the
server oracle; reported possible-peak, repaired-cell, and scalar-fallback
counts; unchanged ordinary/additive tests; then only the existing three ARM
cases. This experiment has a path to retaining scalar semantics while removing
most scalar FP64 work. Full-grid FP64 FFT and exact FP64 conditioned CZT remain
secondary experiments because their code-derived operation reductions are only
about 1.9x and 2.0x.
