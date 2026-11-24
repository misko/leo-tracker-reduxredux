# DS30-0316 tests the nomination handoff's accepting path

**DS30-0316 is the second physical case to use as a control.** Its archived lean worker completed all three ordered, finite two-round nominations and then published without invoking named fallback. The handoff therefore has no consumer on that chronology. An independent rank-only pair on the same signed detections, original archive, cutoff, and offer measured a **0.113 CPU-second** reduction with the grouped rank and preserved all six ordered signed nodes. That prices the producer's rank change alone. The checkpoint's through-exit cost on this accepting case remains unmeasured. [Signed route](history-risk-route.md) · [Rank-only matched inputs and clocks](catalogue-block-bound.md) · [Audit receipt](measurements/nomination-handoff-transfer.json)

## Where the handoff would run

The wrapper executes the same exact ranked producer needed by named inference when the speculative lean cold stage begins. It takes a prepared bank fingerprint, copies the complete rank, and captures a second-phase endpoint, clipped phase vector and c=0 score for each nominated branch. An all-or-none check runs when named fallback requests the same prepared object, region, bound, previous orbit context and ordered nodes. Three unfinished pauses inside the first refresh are insufficient. On a direct named dispatch there is no lean producer. On a lean completion or withholding there is no named fallback consumer. [Source and live admission tests](nomination_handoff.py) · [Cold optimizer checkpoint definitions](cold_finalist_race.py)

| Saved physical input and scope | Original dispatch and finish | Full two-round checkpoints / nominees | Observed cold CPU s | Handoff on that chronology |
| --- | --- | ---: | ---: | --- |
| **DS30-0004, confirmed comparison** | Lean rejects at repair cap, then named | 3 / 3 | 5.034 | **Measured**. Same previous scan, one rank and all three prefixes reused |
| **DS30-0316, original 20 ms** | Lean completes after ambiguous top three | 3 / 3 | 2.192 | No consumer |
| DS30-0008, complete signed mixed packet | Lean finishes only the raced winner and completes | 1 / 3 | 6.304 | No consumer. The archived checkpoint is also incomplete |
| DS30-0138, original 20 ms | Lean completes after ambiguous top three | 3 / 3 | 6.741 | No consumer |
| DS30-0169, original 20 ms | Lean completes after near-face finalist check | 3 / 3 | 1.985 | No consumer |
| DS30-0374, original 20 ms | Lean completes after ambiguous top three | 3 / 3 | 4.565 | No consumer |
| DS30-0402, original 20 ms | Lean completes after ambiguous top three, second nominee wins | 3 / 3 | 8.167 | No consumer |
| DS30-0160, current dispatch | Earlier-orbit health check sends directly to named | No producer | — | No reuse |

The six named saved cases plus the separate complete dense mixed publication yielded **zero additional late named fallbacks**. This is a coverage statement over these receipts. An earlier DS30-0160 worker on the same native packet did enter lean under an older endpoint-recovery experiment. It completed all three two-round fits and then entered an ordinary fallback after an assertion, spending **1.035 CPU s** in cold and **2.440 CPU s** in that fallback. Its trace lacks full cross-route node and prepared geometry identity. The current health gate sends that recording to named before cold lean begins, so the earlier chronology cannot serve as a second positive for this handoff. [Six-case signed ledger](measurements/history-risk-six-case.json.gz) · [Dense full mixed](history-risk-dense-mixed.md) · [Earlier DS30-0160 scope](endpoint-track-repair-0160.md)

DS30-0316's ordered c=0 checkpoints scored **11183.6623, 11188.6934 and 11229.7980**, each with a finite endpoint and a 13-entry phase vector in label order. Their differences and the narrower six-node rank make it a separate accepting case from DS30-0004's seven-node late fallback. DS30-0008 is the denser accepting case with an incomplete prefix. Its receipt logs all three first-refresh pauses but has only one complete score and endpoint. Preserving that chronology would fail the all-or-none check even if a later stage called fallback. The private live guards on exact state, array layout, and object identity require a runtime witness. The saved records establish which structural gates were available and which consumer was called.

## Paid producer and zero reusable work on acceptance

| Matched rank-only component | Ordinary CPU s | Grouped CPU s | Rank-only difference |
| --- | ---: | ---: | ---: |
| DS30-0316, all six nodes equal | 1.322851 | 1.210119 | 0.112732 s |
| DS30-0008 mixed, all seven nodes equal | 4.302574 | 3.918892 | 0.383682 s |

Both rows compare checked rank computations on the same staged input within each recording. Neither credits avoiding a named rank or fit on an accepting route. On DS30-0316 the initial geometry fingerprint, full node copy, and completed checkpoint copies would all be paid even though nothing later consumes them. On DS30-0008 the initial fingerprint and node copy would still be paid and capture would reject the incomplete checkpoint. With the same rank provider and effects held fixed, acceptance has zero gross reuse and positive capture work. If the separately measured grouped-rank gain transferred to a full worker, extra work above **0.113 s** on 0316 or **0.384 s** on dense would consume it. No accepting worker clock with the handoff enabled exists. The measured **26.798 ms** of geometry guarding and **6.329 ms** of checkpoint capture on DS30-0004 include the fallback lifecycle and cannot be used as a measured cost on another recording. [Exact producer measurements](measurements/catalogue-block-bound.json.gz) · [Dense paired rank](measurements/catalogue-block-dense-pair.json.gz) · [Measured 0004 handoff](nomination-handoff.md)

The audit read bounded saved stage receipts only. It opened no waveform, backing catalogue or original recording and launched no solver. The [reducer](nomination_handoff_transfer.py) verifies the six local route hashes against the signed ledger and binds the independent rank comparisons to the saved inputs. Run it with a fresh JSON output path as an account that can read the existing tmpfs stages. Three [component tests](../../../tests/pipeline_eval/test_nomination_handoff_transfer.py) cover incomplete prefixes, accepting and direct-named dispatch, and exact rank-only admission.
