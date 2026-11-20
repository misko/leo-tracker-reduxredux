# Reuse a nested primary grid during the capture retry

Reusing 12 folded anchor sums cut warm complete-detector CPU by **12.0%** on seven held visits with a retry and **3.4%** across all 32 held visits, relative to computing all 22 anchors again under the same nested primary. Both nested implementations returned identical ordered public results, including rejected candidates and gates, on all **48** real visits. The new anchor schedule recovered **18/19** archived held winners and **11/16** forensic targets. [Stage figure](stage.pdf) · [Complete payload and timing seal](qualification-lock.json)

## Folded score and peak ordering

The original primary and retry sets share two anchors. The candidate chooses evenly spaced retry anchors at symbols 2, 30, 58, 86, 114, 142, 156, 184, 212, 240, 268, and 296. The choice was frozen independently of the held outcomes. While evaluating the two primaries it retains each needed receiver's binary64 numerator grid and integer support. An actual peer retry adds the remaining 10 anchors and divides by the combined support. A passing primary's saved sums are released and all sums are cleared at the end of the visit. The only additional retained signal data are the folded grid and support. [Protocol](PROTOCOL.md) · [Prepared bank adapter](../../../../tools/pipeline_eval/variants/nested_anchors.py)

Independent whole-grid audits of **16** reused retry grids found equal integer support and identical ordered coarse epoch/CFO peak keys for every grid. Addition order changed 3,860,823 of 4,479,888 normalized scalar values, with maximum absolute change **4.44 × 10⁻¹⁶**. In the same nested branch the two implementations reproduced all complete receiver output fields, including ranks, rejected factors and both margin gates. Eight selected windows also matched the unmodified installed detector in the original-schedule arm. [Grid arithmetic and peak keys](numerical-grid.json) · [Per-grid differences](coarse.csv) · [Per-visit complete parity](outcomes.csv)

## Detector cost

| Held visits | Original 12/22 (ms) | Nested 12 and fresh 22 (ms) | Nested 12 and add 10 (ms) | Reuse CPU saving vs. fresh 22 |
| --- | ---: | ---: | ---: | ---: |
| Warm, all 32 visits | 324.3 | 322.2 | 311.1 | 3.4% |
| Warm, seven nested retry visits | 445.0 | 467.6 | 411.7 | 12.0% |
| Cold prepared filter cache, all 32 visits | 324.6 | 325.9 | 315.7 | 3.1% |
| Cold prepared filter cache, seven nested retry visits | 438.7 | 478.7 | 425.5 | 11.1% |

Warm timing used five interleaved repeats per selected visit and one thread on CPU 2 or 3. It begins with resident 20 ms dual CI16 and includes full public detector output and native projection. The paired median saving on warm retry visits was 12.4%. Forensic windows and separate coarse-order audits are excluded from those means. On DS26-0162, the four held retry visits used 471.8 and 417.0 ms under fresh and shared 22-anchor calculations. Over its eight held visits, original and shared schedules used 376.8 and 348.7 ms. [All timings](times.csv) · [Per-recording aggregation](summary.json)

The largest retained two-lane partial state was **4,586,552 bytes**, with 2,293,276 bytes per lane at the measured 21 × 13,333 grid. Peak named buffers for one prepared bank entry were 2,072,576 bytes for the direct full-22 arm and 1,212,416 bytes for reuse. Worker high-water RSS across mixed arms ranged from about 170 to 203 MiB, including resident waveform decoding and the other detector stages. [Per-call buffer ledger](times.csv) · [Worker receipts](qualification-lock.json)

## Scientific change from the original primary

Both new nested schedules changed all 32 original held visit payloads. Each performed seven retries with two rescues, as did the original schedule. Six of the seven original physical retry attempts remained, and both original rescued receiver-probes remained rescued. The new schedule dropped one original gated lane and admitted one original negative lane on DS26-0237. DS26-0162 preserved all seven held winners within two samples and 1 kHz and all four forensic target identities. Four of its held original winners were recovered with numerically exact candidate values. [Complete per-lane evidence](lanes.csv) · [Full held receipts](qualification-lock.json)

On the enriched forensic visits, the original detector ran 14 retries and rescued 10 receiver-probes. The nested schedule ran nine retries with six rescues. Nine of the ten original rescued receiver-probes still passed, three by their new primary. All nine specified forensic targets originally supplied by the retry were recovered. Five of the seven original-primary target identities were lost. This distinguishes the numerical reuse result from the scientific effect of substituting the new primary. The complete DS26-0162 waveform run is the separate geographic check for the revised schedule. [Forensic identities](known.csv)

## Reproduce

Use a new scratch directory on the replay host. Run the `freeze` and `run` actions in the trial module on the four frozen cases, with the original installed producer roots and qualified libraries. Run the separate coarse-order audit on the same work directory, then run the results module to generate the stage figure and seal. The C adapter builds in the designated scratch directory. [Trial and binding](../../../../tools/pipeline_eval/qualification/nested_anchors_trial.py) · [Coarse peak audit](../../../../tools/pipeline_eval/qualification/nested_anchors_order.py) · [Component tests](../../../../tests/pipeline_eval/test_nested_anchors.py)
