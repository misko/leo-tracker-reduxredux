# Exact residual reuse on a hard dense finalist

The selected DS30-0008 cold finalist followed full-data association and used 3,895 curved observations in 40 satellite families. This saved fixed-zero branch had the most first-phase objective requests among the archived completed branches. Branch 2 won the original solve. There was no new terminal, position decision, fitted-`c` comparison, or waveform read. The measured endpoint is for branch 1 inside the original supplied region. [Frozen enrollment](finalist-rejection-bound-protocol.md) · [Original trace](measurements/finalist-tangent-DS30-0008.json.gz)

## Archived rejection costs

| Full residual requests | Original phase 1 | Refreshed phase 2 |
| --- | ---: | ---: |
| Initial | 1 | 1 |
| Derivative | 54 | 8 |
| Accepted trust trial | 31 | 8 |
| Rejected trust trial | 28 | 0 |
| Optimizer CPU | 9.488 s | 0.427 s |

The original optimizer accepts a trial only when the exact full score drops by more than `1e-9`. An oracle that already knows every rejection would skip 1.983 historical CPU seconds while retaining the original accepted path. The perfect oracle for just the second and third consecutive rejections would skip 16 calls and 1.192 seconds. The last three rejected calls account for 0.284 seconds and overlap those totals. These are gross bounds for this trace. The closest rejection was `3.64e-11` above its incumbent. The median was `1096.065`. A different Jacobian can change the proposal and radius history even if the full objective tests every acceptance. [Archived census](measurements/finalist-rejection-bound.json)

Eight repeated coordinates had identical full scores within phase 1. Each repeat and its preceding occurrence were rejected trials. They account for 0.561 historical CPU seconds before cache overhead. Three coordinates repeated across the model refresh, and all three full scores changed. In particular, the unchanged phase boundary coordinate moved from score `27707.942083866303` to `28581.467913792592`. A phase-local key can reuse an exact evaluation with no cross-phase spill. The old complete causal solve was 32.484 CPU seconds, of which the cold stage took 15.596. If every archived repeated-coordinate cost were recoverable, it would equal 1.73% of that historical complete solve. The broader all-rejection oracle would equal 6.10%. Neither figure estimates transfer to a different saved route. [Archived census](measurements/finalist-rejection-bound.json)

The existing post-discovery stratified derivative census already left a gross replaceable slice of 0.311 CPU seconds on dense and 0.027 on weak before surrogate cost. The later normal-prior tangent test saved 20 derivative calls and added 54 rejected trials, increasing the two-phase optimizer CPU from 9.915 to 13.810 seconds on this branch. Those results informed the decision to test exact reuse of repeated requests. The memo operates outside the native residual implementation. [Stratified derivative work](optimizer-quadrature.md) · [Finalist tangent experiment](finalist-tangent.md)

## Scoped memo measurement

The memo is owned by one original frozen `NormalPosition.residual` invocation and retains up to eight vectors. It keys exact binary64 coordinates, stores an immutable copy and returns a separate copy on every hit. The original optimizer, full objective acceptance, rank and all full-data rows remain in use. The first reconstruction reached the exact archive rank and stopped before the optimizer when preparation took 12.712 CPU seconds and the conservative projected phase would have exceeded the original 20-second worker limit. That child used 12.961 CPU and 12.973 wall seconds. The single live phase used the authorized 30-second limit with the same enrollment and staged saved inputs. [Memo protocol](finalist-residual-memo-protocol.md) · [Memo implementation](finalist_residual_memo.py)

| Measured boundary | CPU | Wall |
| --- | ---: | ---: |
| Archived optimizer, phase 1 | 9.488353 s | unavailable |
| Memoized optimizer, phase 1 | 8.946413 s | 8.947886 s |
| Memoized phase with exact readout and phase update | 9.047397 s | 9.049188 s |
| Separate direct residual recomputations for the cache audit | 0.551932 s | 0.551730 s |
| Complete saved measurement child through exit | 20.033793 s | 20.042860 s |

The optimizer still made 114 requests. The memo forwarded 106 to the full model. Direct recomputation confirmed all eight hits byte for byte. All 114 ordered coordinate/score requests, 31 accepted steps, 28 rejections, optimizer counters, complete first-phase fit and posterior phase readout matched the archive. The endpoint was `(2.1087646479645628, -2.1075439457854372)` km in the original local frame with score `27707.942083866303` and stop `no_accepted_trust_step`. Peak retained array data was 520,512 bytes. The saved measurement child read 672 process-accounted input blocks and had 12 major faults. Its detector and orbit inputs were the already staged saved documents, and it performed no waveform acquisition. [Bound phase receipts](measurements/finalist-residual-memo.json.gz)

The observed optimizer difference was 0.542 CPU seconds, or 5.71% of the historical phase-1 optimizer clock. Dividing that difference by the historical full-solve clock gives 1.67%, for scale only. This is one current phase against a historical control on the same saved branch. The historical 10.053-second wall clock covered two phases and does not supply a matched wall delta. There was no fitted-`c` or geographic-result measurement because the trial ended inside a single fixed-zero finalist. The exact cache is a small potential saving on this repeat-heavy phase. Transfer, savings on the winning branch and aggregate cost effectiveness remain open. [One-phase driver](finalist_residual_memo_trial.py) · [Bound phase receipts](measurements/finalist-residual-memo.json.gz)
