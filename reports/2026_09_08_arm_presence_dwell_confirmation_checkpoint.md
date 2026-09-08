# Whole-dwell GLRT confirmation: timing reuse and exact execution optimizations

2026-09-08. **Engineering progress, not a deployed or qualified classifier.**
All new execution used archived or synthetic IQ. Production acquisition,
FPGA, kernel and flashed firmware were unchanged. Actual LIBIIO transport
integration, whole-dwell classification quality and unchanged live duty remain
unproven; the active goal is not complete.

## Outcome

The native experiment now measures a complete 120 ms single-RX screen followed
by ranked 20 ms fractional GLRT confirmations. Prefix timings include the
screen and every preceding confirmation, not merely the last detector call.
It supports a blind comparator, direct timing reuse, and a two-resolution
policy: screen all six intervals cheaply, then estimate timing at higher
resolution only inside selected intervals.

Two exact execution optimizations preserve the tested scientific outputs:

1. **Integer folding for the blind search.** Accumulate original CI16 power
   and lag products with widening int64 arithmetic, using NEON on ARM. Keep
   the original FP64 path when tone conditioning has changed the working IQ.
   All eight original timing neighborhoods, signed-power reranking, CFO search
   and fractional confirmation remain. This saves little end-to-end time in
   the measured workload; it is opt-in, not a claimed timing-gate success.
2. **Prune unused screen dependencies.** The existing projection reads two
   native timing cells for each output bin. Fold only their dependencies
   (rounded out to SIMD groups), and normalize only cells actually consumed.
   This is the same statistic, not a narrower screen or a new hypothesis grid.
   An all-cells build remains available as a qualification comparator.

On the small ARM replay, the latter reduced the 5 MS/s blind-path screen from
28.3 to 17.5 ms mean CPU. End-to-end blind top-one p99 improved from about
120 to 110 ms, still above the 100 ms target. The faster seeded path reaches
about 90 ms p99, but loses reference associations and is not an acceptable
drop-in replacement. Further optimization and classification qualification
are required before live deployment.

## What timing reuse did—and did not—preserve

Given the correct integer seed, seeded confirmation reproduces the blind
detector's fractional computation. That does not mean a cheap screen supplies
the correct seed. The low-resolution score can rank a window usefully while
its timing peak is aliased far from the reference epoch.

An initial high-resolution-dispatch unit test also incorrectly assumed the
512-bin screen always ranked its noisy synthetic signal window first; the
5 MS/s example selected another window. The dispatch test now isolates routing
with zero-valued other intervals. This is not a sensitivity fix: the separate
historical quality gate below remains failed and is not weakened by that test.

The corpus is the same previously inspected 96 dwells / 576 temporal probes,
RX1, four scans, both rates and all eight channel edges. It is **development
data**, not fresh holdout. Each multiresolution evaluation contains 384 dwell
executions: 96 inputs, two timing-grid settings per rate, two modes. Its
1,152 blind window outputs match the previously frozen candidate fields.

For a 512-bin screen, with selected-window timing grids 2048 at 2.5 MS/s and
4096 at 5 MS/s:

| Confirmed ranked intervals | Blind reference-associated dwells | Seeded reference-associated dwells |
|---|---:|---:|
| One | 20/35 | 18/35 |
| Two | 24/35 | 21/35 |
| Three | 28/35 | 24/35 |
| Six | 30/35 | 26/35 |

The denominator is 22 reference-positive dwells at 2.5 MS/s and 13 at 5 MS/s.
These are associations with historical fractional GLRT, **not independently
established sensitivity**. Additional flags without association remain
unresolved RF evidence, not automatically false alarms or new detections.
The raw results retain all unsuccessful grid settings as well as successful
ones; no threshold or reference fixture was changed to improve these counts.

Nine individual reference-associated windows were lost by the cheaper seeded
policy relative to blind confirmation. In all nine, tone removal was inactive.
Eight seed differences were large (61 to 3,425 samples in magnitude); one was
one sample away but did not yield the same complete CFO/fractional result.
Thus raw-versus-tone-conditioned ordering does **not** explain these particular
misses. Retaining only the strongest differential peak also discards the blind
search's alternative neighborhoods and signed-power evidence. Merely adding
a one-sample local search would not repair the large errors.

## Measured ARM cost

Each run used eight distinct archived dwells, both modes, three repeats:
48 whole-dwell executions / 288 confirmation windows. The table's p99 therefore
has only 12 observations per rate/mode; it is not a worst-case bound. Process
CPU time is visibly quantized on this ARM. Wall latency and observed maxima
are retained in the linked machine-readable results. File loading, template
setup and workspace creation occur outside these steady-state timings.

| Execution policy | 2.5 MS/s top-one CPU p99 | 5 MS/s top-one CPU p99 |
|---|---:|---:|
| Two-resolution seeded, before exact optimizations | 50.0 ms | 100.0 ms |
| Blind search with integer folding, stage-instrumented | 70.0 ms | 119.9 ms |
| Blind search plus dependency-pruned screen | 68.7 ms | 110.0 ms |
| Seeded plus dependency-pruned screen | 50.0 ms | 90.0 ms |

The final blind 5 MS/s mean is 99.1 ms, but its tail still fails the target.
Two blind confirmations cost 176.5 ms mean / 180.0 ms p99 there; the extra
quality from additional windows does not fit the proposed every-dwell budget.
No pooled average across sample rates is used to conceal the 5 MS/s miss.

The stage-instrumented blind 5 MS/s run, before screen dependency pruning,
measured approximately 28.3 ms screen, 1.7 ms conversion, 29.2 ms coarse search,
21.6 ms fine search and 15.8 ms fractional confirmation, on average. Tone
handling and remaining bookkeeping are included in the 106.6 ms total, not
all itemized in those components. Quantized per-stage p99 values must not be
added together. The largest remaining opportunities are the coarse/fine
searches and the cost of enough confirmations to recover whole-dwell evidence.

## Validation and provenance

- Both exact optimizations preserve all ranks, observations and **2,304 full
  candidate structures** across the 384 desktop executions, relative to the
  original multiresolution run—not just threshold decisions.
- The final 48 ARM executions / 288 confirmation windows match the original
  desktop outputs, including rank order, epochs, fractional CFO/score evidence
  and nuisance fields, with the existing comparison tolerances.
- A separate ARM self-test checks every folded output cell against an
  independent scalar integer reference for 24 rate/length/input combinations,
  including INT16 extrema, alternating signs, zero input and partial tails.
- The final **775-test** component suite covers detector, ranker, worker/pool, frame codec,
  host binding, replay accounting and malformed inputs. See the execution
  receipt for the final test count and commands. These tests do not imply
  actual LIBIIO provider integration has been implemented.
- ASan/UBSan with leak detection enabled passes 16 final full-dwell executions
  (96 confirmation windows), plus 24 standalone folding cases. This is bounded
  replay coverage, not fuzzing or exhaustive memory-safety proof.

ARM work used spare serial `104000b29905000e17000800065934759d` on its pinned
LAN connection at `192.168.1.15`. No IIO context or radio device was opened by
the replay programs. The excluded serial was not accessed. New integer-fold,
stage and dependency-pruned replay commands checked identity and disabled RX
buffers before/after every invocation and exited successfully. The older
multiresolution job's full output was recovered after its process ended; its
original command-exit receipt was unavailable. A new read-only postflight
found the expected idle spare. That recovery is not retroactive proof of all
of the older job's guards.

The final ARM binary is
`e82a70558b74be19af5759d2eafc5650fc15abafaaa18e49a78ac493c1f9065c`;
its retrieved output matches remote SHA-256
`83f6be4bcbd82f2618895e3b12051829fa1076cb5e14a914ad66e425b78740fd`.
Build receipts, source/input hashes, compressed numerical outputs, timing
summaries and unsuccessful policies are in
[the evidence directory](evidence/2026_09_08_arm_presence_dwell_confirmation/).
No binaries or raw IQ are committed.

## Decision and next work

Keep the blind search as the quality comparator; do not silently replace it
with the faster but less complete timing-reuse policy. The exact screen
optimization is a useful reusable improvement, not completion of the goal.

Next, profile and reduce the remaining coarse/fine costs while preserving
alternative timing hypotheses, and qualify a bounded whole-dwell decision on
fresh data and independent interference controls. Then integrate full-dwell
collector sizing and the negotiated LIBIIO metadata/final-drain path. The
existing frame codec alone does not implement that transport. Original block-
arrival replay and explicitly authorized live disabled/enabled duty comparison
remain required. No deployment, merge to remote main, or unchanged-live-duty
claim is made at this checkpoint.
