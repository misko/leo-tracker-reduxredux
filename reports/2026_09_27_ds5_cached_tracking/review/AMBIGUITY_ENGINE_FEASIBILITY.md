# Feasibility of a visit-wide timing/CFO ambiguity engine

This is a source and operation-count review. It does not implement a new
detector, open holdout IQ, or make an ARM timing claim. The conclusion is that
the literal full timing-by-CFO surface proposed in
`TEN_X_REMAINING_BUDGET.md` is not a credible route to the 0.260 ms
per-receiver-visit server budget. A sparse proposal engine can still be tested,
but it is a different detector and must retain the existing exact/control GLRT
as its decision stage.

## Geometry in the frozen research profile

The profile supports 2.5 and 5 Msps, a 20 ms confirmation interval, and one
candidate. Its relevant flags are `FAST_FINE_FFT`, two fine frames, two epoch
frames, a +/-200 Hz conditioned search at 100 Hz spacing, a 512-bin hybrid
rank, lag-4 differential acquisition, tone nuisance removal, and 64-symbol
diverse final GLRT scoring. The source accepts only a template length
`nearbyint(rate/750)` and allocates one 20 ms confirmation window
([presence.c:307](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/presence.c:307)).

| Quantity, per receiver | 2.5 Msps | 5 Msps | Source/derivation |
|---|---:|---:|---|
| Samples in 20 ms | 50,000 | 100,000 | `rate/50` |
| Samples in 120 ms | 300,000 | 600,000 | six windows |
| Native timing cells `n` | 3,333 | 6,667 | `nearbyint(rate/750)` |
| Rank timing cells/window | 512 | 512 | frozen profile; valid range at [window_rank.c:156](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/window_rank.c:156) |
| Fine FFT size | 4,096 | 8,192 | next power of two at [presence.c:344](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/presence.c:344) |
| Fine CFO spacing | 610.3515625 Hz | 610.3515625 Hz | `rate/fine_size` |
| CFO cells over [-400, 400] kHz | 1,311 | 1,311 | aligned bins -655 through +655 |
| Conditioned CFO cells/candidate | 5 | 5 | +/-200 Hz inclusive at 100 Hz |
| Samples in each 64-symbol GLRT region | 704 | 1,408 | `symbol_start(66)-symbol_start(2)` |

The 1,311 count follows the actual endpoint code: the range is first aligned
to FFT bins ([presence.c:837](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/presence.c:837)) and `grid()` includes its endpoints
([presence.c:459](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/presence.c:459)). The code then evaluates one shared input FFT per supporting frame and reads the requested bins
([presence.c:477](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/presence.c:477)). It does not currently construct a timing-by-CFO surface.

## Literal full-grid lower bound

A native-timing by fine-CFO surface has `6*n*1311` cells per 120 ms visit.
This is already too large even if each cell were magically computed with one
operation and the engine retained only one score.

| Surface, per receiver visit | 2.5 Msps | 5 Msps |
|---|---:|---:|
| Cells/window | 4,369,563 | 8,740,437 |
| Cells/six-window visit | 26,217,378 | 52,442,622 |
| Required cell rate in 0.260 ms | 100.84 Gcell/s | 201.70 Gcell/s |
| One FP32 score surface | 100.01 MiB | 200.05 MiB |
| Exact + control FP32 surfaces | 200.02 MiB | 400.11 MiB |
| Write bandwidth for those two surfaces in 0.260 ms | 806.7 GB/s | 1,613.6 GB/s |

Using the final 100 Hz conditioned spacing over the full carrier interval
would make 8,001 CFO cells. That is 160,003,998 cells at 2.5 Msps and
320,056,002 at 5 Msps, before exact/control duplication. Streaming a top-K
heap avoids the surface writes, but it does not avoid evaluating 101 or 202
billion fine-grid cells per second. Both receivers double all visit counts.

These are lower bounds, not estimates of a GLRT. One fine ambiguity value
actually uses 300 known symbols over each of two frames, normalization, and a
magnitude ([presence.c:491](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/presence.c:491)). One final ambiguity value is more expensive still. An FFT can share work along one axis, but a full discrete delay-Doppler ambiguity function still has every delay-Doppler output. There is no algebraic collapse from 26/52 million outputs to a bounded top-K result without first using a proposal statistic or changing the searched grid.

## What the existing detector actually computes

The existing pipeline avoids this surface by staging the search. The dwell
first ranks all six windows and then confirms only the declared maximum number
of windows ([dwell.c:52](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/dwell.c:52)). With the frozen maximum of one:

1. **Visit rank.** Each 20 ms window folds 15 frame starts at lag 4. Because
   the hybrid projection forces a dense fold, this is exactly 299,946 complex
   lag products at 2.5 Msps and 600,006 at 5 Msps over six windows. Two
   projection statistics per window each perform two 512-point FP32 FFTs, for
   24 FFT512 calls per visit. The implementation and shared fold are at
   [window_rank.c:234](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/window_rank.c:234) and
   [window_rank.c:355](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/window_rank.c:355).
2. **Selected-window differential proposal.** The selected 20 ms window is
   folded across up to 16 frame starts; one 4,096/8,192-point correlation
   proposes at most eight timing neighborhoods, and only native local cells are
   rescored ([coarse_differential.h:68](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/coarse_differential.h:68)).
3. **CFO acquisition.** Two fine FFTs inspect 1,311 bins, then two frames of
   five 100 Hz conditioned dot products select the acquired CFO
   ([presence.c:837](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/presence.c:837)).
4. **Timing and decision.** Five integer timing cells receive a two-frame
   exact/control GLRT. An interior log-parabolic timing result is rescored with
   the final fractional, full-support GLRT
   ([presence.c:889](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/presence.c:889)).

For an upper-support candidate, the five-cell lattice consumes 7,040/14,080
received sample positions and 14,080/28,160 exact/control complex MACs at
2.5/5 Msps. It invokes 30 FFT128 and 10 FFT512 calls. The final fractional
call can support at most 15 frames in a 20 ms window, consuming
10,560/21,120 received positions, 21,120/42,240 exact/control complex MACs,
32 FFT128 calls, and two FFT512 calls. A noninteger timing offset also performs
16 real-tap complex interpolation terms at each received position: at most
168,960 terms at 2.5 Msps and 337,920 at 5 Msps. These counts follow the
64-symbol inner loop and 16-tap interpolator at
[presence.c:608](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/presence.c:608); the nominal frame limit is 16, but the sixteenth 1/750 s frame cannot fit this region in a 20 ms interval.

The nuisance fit is another material pass. In its worst applied path it reads
the window for energy, three lag sums, a least-squares amplitude, and
subtraction: `6*window_samples-(256+4096+16384)`, or 279,264 sample terms at
2.5 Msps and 579,264 at 5 Msps, plus one 4,096/8,192 FFT. Its ordering is part
of the detector: it modifies the selected working window before acquisition
([tone_nuisance.h:6](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/tone_nuisance.h:6)).

The fixed development-prefix receipt confirms that these are not merely
theoretical side costs. Median rank CPU was 0.268/0.508 ms at 2.5/5 Msps;
selected-window confirmation was 0.699/1.566 ms; nuisance was 0.044/0.103 ms;
and final confirmation was 0.174/0.149 ms. This older server receipt is a
component diagnostic with a separately pinned binary, not a current ARM or
cross-profile speed comparison. Still, rank alone already exceeds the
0.260 ms whole-call budget at 2.5 Msps and is almost twice it at 5 Msps.

## Reuse that preserves the statistic

The following transformations can preserve the mathematical terms, subject to
numerical equivalence tests because their reduction order may change:

- Reuse one fine input FFT across every requested CFO bin. The implementation
  already does this.
- Reuse interpolated received samples, CFO rotations, and support checks across
  the exact and rolled-control templates. The GLRT already shares the received
  value and rotation before its two template accumulations
  ([presence.c:659](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/presence.c:659)).
- Evaluate the five neighboring integer timing cells in lanes while streaming
  overlapping input, while retaining each cell's frame boundaries, ceilings,
  spectra, and tie rules. This saves loads; it does not reduce the five sets of
  correlations.
- Stream the best K proposal cells rather than storing a proposal surface. This
  preserves a proposal if traversal and tie order remain frozen. It does not
  reduce cell arithmetic.
- Batch same-sized FFTs and reuse template transforms/twiddles. Template and
  rotation tables already live in the workspace
  ([presence.c:131](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/presence.c:131)).

The following shortcuts change the detector statistic or its nuisance model:

- Folding frames before the final score. The GLRT takes per-frame symbol
  correlations, transforms them, accumulates squared spectra, and separately
  accumulates squared L1 ceilings ([presence.c:693](/home/mouse9911/gits/leo-adaptive-position-deploy/src/leo/analysis/native_presence/presence.c:693)). Coherent frame folding cannot be moved through those nonlinear operations.
- Treating the normalized fine FFT score as the final exact/control GLRT. Fine
  acquisition coherently correlates 300 symbols and averages frame magnitudes;
  final scoring uses 64-symbol spectra, a different normalization, early/late
  diversity, and residual-CFO fitting.
- Applying one nuisance estimate to all six windows or computing rank on
  tone-subtracted samples. Current rank sees original visit IQ, while nuisance
  selection and subtraction happen only after a window is chosen. Moving it
  changes both window ordering and the data scored.
- Replacing the broad CFO search with lag-product phase. That is a valid new
  proposal statistic, not an identity. The already frozen lag-4 phase-CFO
  experiment lost 5 of 36 development reference positives through wrong CFO
  aliases and ran at 0.881x overall, so its cheap proposal is not evidence that
  this shortcut works.
- Precombining fractional interpolation and pilot coefficients. The linear
  correlations can be transposed, but the per-symbol `cabs` ceiling and later
  nonlinear spectra must remain. The completed coefficient prototype was
  1.047x slower once setup was charged.

## Bounded next prototype

Do not implement the full two-dimensional surface. The only proportionate next
experiment is an isolated **lag-3 phase proposal kernel** with a hard cost gate,
followed by the unchanged nuisance and exact/control decision path only if that
gate succeeds.

Lag 3 is chosen from geometry rather than outcomes. Its principal phase covers
`+/-rate/(2*3)`: +/-416.7 kHz at 2.5 Msps and +/-833.3 kHz at 5 Msps, so the
declared +/-400 kHz interval has no carrier alias at either rate. The kernel
would replace, rather than add to, the existing lag-4 visit fold; retain the
complex matched-correlation value at each selected rank peak; convert its phase
to one CFO proposal; and stream a frozen small number of timing peaks. Its
dense fold is 299,952 lag products at 2.5 Msps and 600,012 at 5 Msps. No
timing-by-CFO surface or full-CFO fine FFT is produced.

This proposal changes the rank statistic and remains vulnerable to mixtures,
close interferers, and phase bias. The prior lag-4 result means it must be
qualified from scratch and must not use fallback triggered by a known reference
outcome. A minimal prototype should therefore expose only:

- ranked `(window, integer_epoch, phase_cfo, proposal_score)` tuples;
- complete natural-stride CI16 ingress timing, with one warmup and at least
  three counterbalanced repetitions;
- exact comparison of its tuple determinism and boundary support; and
- a development/control scientific pass only after freezing lag, peak count,
  tie order, and any local CFO offsets.

Set an early **0.080 ms server CPU target at both rates** for the complete
proposal kernel. That leaves 0.180 ms for nuisance handling, exact/control
confirmation, result formation, and caller overhead. Missing that target ends
the experiment before detector replay, because the currently measured 5 Msps
nuisance plus final GLRT already consume about 0.252 ms and also require
optimization or a separately qualified statistic change. Passing the proposal
target still does not establish a 0.260 ms detector; the only valid performance
gate remains the complete per-receiver call.

The practical decision is therefore: reject the full 2-D ambiguity engine,
retain sparse proposal-plus-confirmation staging, and use the lag-3 kernel only
as a cheap feasibility test. If the complete call cannot reach 0.260 ms without
removing nuisance support or replacing the exact/control GLRT, then the server
10x target requires an explicitly new detection statistic rather than an
algebraic optimization claim.
