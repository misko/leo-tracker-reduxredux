# Whole-catalogue bounds in the cold association

The group certificate identified 97.2% of profile rows on physical DS30-0316 and 95.1% on dense DS30-0008 after existing exact caches. The counts apply to the original fixed-state white association requests. Each kept the original cadence of 16 actual association calls and reproduced the complete archived sequence of unique rank signatures. Prior phase proposals, final ranking likelihoods, the causal orbit bank and all later paid competitors remained available. [Frozen protocol](catalogue-block-bound-protocol.md) · [Saved measurement receipts](measurements/catalogue-block-bound.json.gz)

## What the boxes prove

Sort each track's nominal catalogue by the signed Doppler contrast between two early and two late groups of native observations. Make consecutive groups of 16 orbits in that order. Within the track select one, two or four real observations in each of four chronological quarters, with equal group counts. Three mutually orthogonal sign contrasts cancel any shared frequency offset, including every signed native alias and the common Gaussian track bias. Their squared norm is a lower bound on the full residual energy. The distance from the observed contrast vector to a block's componentwise min/max box is a lower bound on every member's norm. Padding accounts for floating-point comparisons. The box is built from the exact nominal orbit predictions at the original anchor and RF, and is retained for repeated queries at that anchor. Orbits with an already changed phase bypass the nominal certificate and use their original exact predictions.

A block may lose all its unchanged members only when the lower bound fails both the original 450 Hz RMS condition and the cost of a feasible, fully visible row. A block whose maximum elevation is negative at a shared sampled epoch fails all-time visibility. Every original tie, finite ungated minimum and possible compatible visible competitor is protected. The block containing catalogue row zero is protected for the original all-invisible fallback. The independent incumbent looks at one member of the closest sampled box with eligible rows, checks its actual full-track visibility and evaluates its complete Gaussian upper bound. When the attempt cannot supply an incumbent, the RF certificate retains the block. [Proof arithmetic](catalogue_block_bound.py)

| After the existing exact association and gather caches | DS30-0316 medium | DS30-0008 dense |
| --- | ---: | ---: |
| Original profile calls / row profiles | 624 / 918,528 | 1,792 / 2,644,992 |
| Block requests | 57,408 | 166,656 |
| Blocks with 0 / 1 / 2 required original rows | 56,160 / 1,248 / 0 | 163,072 / 3,559 / 25 |
| Shifted rows held for exact profiles | 8,229 | 70,560 |
| Rows eliminable by exact-score and compatibility oracle | 899,799 | 2,544,573 |
| Rows proved outside using free original winning score | 894,406 | 2,530,139 |
| Rows proved outside using feasible independent incumbent | 892,716 | 2,515,096 |
| Genuine complete blocks rejected by feasible bound | 53,378 | 125,460 |
| Additional mixed blocks whose nominal portion is rejected | 2,650 | 35,383 |
| Rows rejected by common sampled horizon alone | 223,872 | 656,864 |
| Atlas builds / cache hits | 195 / 429 | 560 / 1,232 |

The oracle sees full scores, all-time per-row visibility and original qualification. It gives no timing credit for an actual branch choice. The independent-bound observer used actual incumbent selection and checked the resulting exclusion mask against every original paid competitor. It made no exclusions during the two control runs. All independent incumbents were finite. Earlier individual contrasts gave all-orbit gathers and full-set visibility to their bound, and smaller profile arrays changed released diagnostic floats. Grouping permits one box query to stand for a block and gives an opportunity to skip its original full-track gather. [Prior per-curve study](full-family-amortized.md) · [Original rank and output caches](cold-exact-budget.md)

## Cost ceilings

| Saved rank or counterfactual cost, CPU s | DS30-0316 medium | DS30-0008 dense |
| --- | ---: | ---: |
| Archived exact rank, without this observer | 1.378 | 4.438 |
| Archived complete numerical solve | 8.778 | 23.645 |
| Original curve calls timed inside observer | 0.368 | 0.939 |
| Feasible-bound row-weighted gross model | 0.358 | 0.893 |
| Index work and feasible query including incumbent | 0.141 | 0.396 |
| Optimistic difference before survivor scoring and output | 0.217 | 0.497 |
| Whole observed curve calls entirely avoidable | 0 | 0 |

The row-weighted model grants each removed row its proportional share of original per-call time. Every request still has at least one surviving row and shares fixed work, such as reduction setup, with the rejected rows. These estimates do not measure saved seconds. The independent historical dense profile attributed 1.673 CPU s to all broad association, 1.052 to the full curve child including its diagnostics and 0.843 to the white profile alone. These are inclusive levels. Their work cannot be added across boundaries. The additional observer-only full visibility and competitor audit cost 0.151 s on medium and 0.431 on dense. The two diagnostic processes took 6.639 and 12.298 CPU seconds, with zero system input blocks. No waveform, finalist fit, fitted-`c` arm, new exit decision or survey comparison ran in either. [Stage clocks and rows](measurements/catalogue-block-bound.json.gz)

## Medium saved rank pair

| Cold rank on identical saved observations | Original | Grouped prototype |
| --- | ---: | ---: |
| CPU | 1.322851 s | 1.210119 s |
| Wall | 1.323230 s | 1.210212 s |
| Curves using reduced row scorer | 0 / 624 | 624 / 624 |
| Candidate row profiles sent to compact evaluator | 918,528 | 25,812 |

The prototype bypasses full-track gathers for excluded nominal groups. It uses compact Fortran arrays for survivor rows and an original-height, zero-padded Fortran matrix for the stock bias multiply. This boundary preserves the bias kernel's original leading dimension, which was lost in the individual-contrast prototype. The full-height multiply still touched **43,194,368 cells**. All **892,716** certified removals were exercised, and no call needed the full fallback. Every retained rank's complete canonical node, signed aliases, ordered seed rows and unrounded diagnostics matched, including the digest `sha256:107ae9362f1e628bb0f03f647e607307121f7354a362d951982ef31b8418e76a`. The comparison finished before finalist fitting. [Prototype](catalogue_block_rank.py) · [Paired receipt](measurements/catalogue-block-bound.json.gz)

The observed saving was **0.113 CPU seconds**, 8.52% of this medium rank. As a scale comparison, it is 1.28% of the archived medium complete solve, which was not rerun with the prototype. The pair's child used 7.214 CPU and 7.216 wall seconds with no storage input blocks. Dense activation was outside the frozen scope. Runtime and exactness on another BLAS build, a different nominal/mixed atlas or a complete position and geographic decision remain unmeasured. One materially different rank target is to fuse the still-paid nominal sufficient-statistics passes before phase nomination while retaining every matrix row and its original top-k order. The prior dense profile puts a 0.798 CPU-second inclusive ceiling on that separate statistics boundary. [After-cache dense timing](cold-exact-budget.md)

## Reproduction

Use the pinned installed payload, the earlier `cold_exact_budget.py` worker and the same staged packet and archive roots recorded in the receipt. Use a fresh tmpfs output for each command. Run `catalogue_block_bound_trial.py run medium OUT` and `run dense OUT`, then `run medium OUT --prototype` under the shared Gauss `flock`, CPU 2, nice 15 and I/O priority 7 with one mathematical thread. Set `PYTHONPATH` to this checkout's `reports/ALGO08/v3`, checkout, and `src`, plus the frozen release `src` and root. The child runs in the release venv, and no original waveform access is permitted. The first medium observer accidentally nested the existing centre cache, raised `Unexpected ALGO08v3 discovery statistics`, and let the installed fallback complete from staged detections before its audit was rejected. Its 18.613 CPU-second receipt has zero input blocks and no waveform access. The corrected launcher uses the original cache once and forbids a full fallback. Five focused component tests passed. [Trial runner](catalogue_block_bound_trial.py) · [Component tests](../../../tests/pipeline_eval/test_catalogue_block_bound.py)
