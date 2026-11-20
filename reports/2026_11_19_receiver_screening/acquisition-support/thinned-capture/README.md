# Thinned full-epoch acquisition in the capture-era detector

The two-frame, four-anchor proposal recovered **19 of 160** original first-pass coarse basins and **11 of 33** original final positive records. Its median dual-receiver CPU fell from **1,404.32 to 417.85 ms** and remained above the 20 ms target. The wide regional receiver matched **32 of 33** original positive records at **14.22 ms** median CPU. The installed releases authenticated all four recordings and reproduced the original probe bytes before comparison. [Protocol](PROTOCOL.md) · [Qualification](qualification.json)

## Held comparison

The two warm, rotating triplets on each of ten admitted visits ran on CPU 4. Four visits had zero original positives and six had at least one. One additional recorded visit kept its original capture exclusion. Every mode used the same two physical receivers and the same raw CI16. Timing begins with an in-memory visit and ends at the complete detector response. Archive decoding and positioning sit outside this clock.

| Result | Capture-era original | Thinned and exact rescore | Wide regional |
| --- | ---: | ---: | ---: |
| Final positive records | 33 | 14 | 47 |
| One-to-one matches to the original | 33 | 11 | 32 |
| Missed original positives | 0 | 22 | 1 |
| Additional positives | 0 | 3 | 15 |
| Original-positive visits with any positive output | 6 / 6 | 2 / 6 | 6 / 6 |
| Median detector CPU | 1,404.32 ms | 417.85 ms | 14.22 ms |
| Median detector wall | 1,412.43 ms | 421.02 ms | 14.22 ms |
| p90 detector wall | 2,695.83 ms | 734.52 ms | 15.98 ms |
| Calls at or below 20 ms wall | 0 / 20 | 0 / 20 | 20 / 20 |

Positive matching uses the original two-sample and 1 kHz alias-aware comparison. Additional positives are relative to the original detector. Both alternatives preserved zero positives on all four zero-positive real visits. Exact coarse-key recall and purity were both 19/160 for the thinned first pass. Wide shared 33/160 exact keys in its emitted shortlist. That wide count follows its regional coarse gate, while the capture counts come from the first eight basins passed into the original acquisition refinement. [Wide shortlist bindings](wide-shortlists.json) · [DS26-0036](DS26-0036.json.gz) · [DS26-0237](DS26-0237.json.gz) · [DS29-0082](DS29-0082.json.gz) · [DS29-0174](DS29-0174.json.gz)

## Where the losses occurred

The thin first pass retained all 13,333 epochs and 21 supported CFO cells at each epoch. It used frame indices 3 and 11 and four stratum-midpoint anchors. Up to 32 peaks nominated merged ±6-epoch intervals for the same native kernel at every active CFO and with the entire original frame and anchor support. Over 42 acquisition invocations, including peer-receiver retries, it rescored 302,484 of 11,759,706 original cells, or 2.57%. The 215,628 directly comparable cells all matched the original full native grid bit for bit. The screened DS29-0174 release and unmatched retry shapes have fewer directly comparable cells.

Only 19 of the original 160 first-pass top basins fell inside a nominated interval with their required exact neighbors. Exact rescoring recovered all 19. The misses in this panel originated in nomination coverage. Empty and seeded Gaussian controls produced zero positives in either band in all modes. On the upper weak-plant control, the thinned path returned zero positives and the original produced seven. Both wide-band high-CFO planting controls retained matched original positives after thinning. [Stage clocks and all control counts](qualification.json)

Across the held triplets, the isolated thin proposal, 32-peak selection, and exact rescore used 1,144.06, 1,225.25, and 1,250.58 CPU ms, respectively. The remainder of the thinned detector after subtracting its coarse-grid and final peak-selection clocks still took **246.49 ms** median CPU. This arithmetic bound describes the measured pipeline with original refinement and the thinned shortlist. The tracked coarse NumPy buffers accounted for up to 3,843,984 bytes. Process high-water was 234,100–246,836 KiB for the paired harness, including the installed Python environment, full parent grids used for parity, and the wide context.

## Reproduction

Run `tools.pipeline_eval.qualification.thinned_capture_eval freeze` before opening the held candidate results. Run the same module with each recording ID under the corresponding [installed capture runtime](../../detector-origins/lineage/README.md), on one core. This variant calls the existing installed native kernel directly, with no new binary build. Use `tools.pipeline_eval.qualification.thinned_capture_results <local-work> --wide-case <recording>` for each wide shortlist audit and omit `--wide-case` to package the evidence. [Frozen source and IQ roster](source-lock.json) · [Evidence hashes](evidence-lock.json)
