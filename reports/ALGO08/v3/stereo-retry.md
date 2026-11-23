# A single stereo retry decision pays for both antennas

The frozen bilateral agreement rule removed all accepted 8 ms disagreements by sending **every pair** to the full 12 ms primary, including the 114 dense and 13 weak visits already within tolerance on both lanes. A looser paired margin rule removed **10 of 19** accepted dense disagreements and none of the five weak disagreements. It also expanded the original dense retry count from **182 to 242** lanes. Neither passes the cost and agreement screen. [Frozen rules](stereo-retry-protocol.md) · [Per-visit decisions and clock bounds](measurements/stereo-retry.json.gz)

## What the pair can tell the receiver

The comparison uses the actual signed 8 and 12 ms outputs on **168 dense nonanchor stereo visits** from DS30-0008 and **18 weak DS26 stereo visits** from five recordings. Dense visit and antenna identities match across apertures, and the unchanged full anchors are excluded. Both lanes keep their own scores and output. The bilateral rule accepts only when both 8 ms margins clear **0.050** and the antennas agree within **two wrapped samples and 250 Hz**. The paired margin control checks only the two margins. A retry takes each antenna's own archived 12 ms result. Scientific factors are never copied between lanes.

| Routing decision | Dense paid lanes / 336 | Dense disagreements left | Weak paid lanes / 36 | Weak disagreements left |
|---|---:|---:|---:|---:|
| Perfect independent answer-key oracle | 59 | 0 | 5 | 0 |
| Perfect stereo answer-key oracle | 108 | 0 | 10 | 0 |
| Frozen independent margin | 182 | 19 | 2 | 5 |
| Paired margin | 242 | 9 | 4 | 5 |
| Bilateral margin, timing and CFO | 336 | 0 | 36 | 0 |

Among the **47 dense** and **16 weak** pairs already confident on both antennas, four dense and seven weak pairs satisfied the timing test. None satisfied the signed-CFO test. The earlier physical partner audit also saw no match when requiring two wrapped samples and signed CFO within 1 kHz on its separate panel. The prior stereo FFT study measured slower exact batched transforms, and the earlier blind occupancy rule missed physical factors. Those experiments tested waveform processing before or within acquisition. This rule uses only the published 8 ms outputs to decide whether to spend a second search. [Earlier partner audit](../single-core-2x/receiver-lanes.md) · [Independent stereo FFT comparison](stereo-fft.md) · [Blind occupancy comparison](occupancy.md)

## Retry CPU budget

The dense oracle has **49** visits with one disagreement and **five** with two. Paired retry adds **49** otherwise unnecessary antenna calls to the same 54 visits. Every weak disagreement is alone on its visit, so paired retry doubles those five calls. These oracles match the parent factor within its documented tolerance. No position solve or position-quality claim comes from the comparison.

The archive has the measured aggregate native cost of the oracle's actual disagreeing lanes, but lacks clocks for their opposite partners. With the same archived per-lane prices, the paired oracle must cost at least the independent oracle. Its upper bound is the sum of all first looks and all 12 ms calls. On dense, repeat two already loses by **11.37 ms** if the additional partner calls are free. In repeats one and three the 49 extra lanes would have to average at most **210 µs and 192 µs**, respectively, versus a measured overall direct mean near **1.05–1.09 ms per lane**. On weak, the five additional calls can average at most **906 / 614 / 1,198 µs** in the three repeats. The archived clocks alone cannot rule out those partner prices.

| Native CPU, median of three repeat prices | Dense ms | Weak ms |
|---|---:|---:|
| Direct 12 ms, measured | 353.18 | 45.39 |
| Independent oracle, measured component sums | 356.13 | 39.40 |
| Stereo oracle, observed independent sum plus mean price for added partners | 407.73 | 45.70 |
| Paired margin, mean price for every restart | 543.67 | 37.79 |
| Bilateral rule, all first looks plus every direct restart | 640.44 | 78.14 |

The equal-mean rows assign the direct population mean price to calls whose actual subset prices are missing. They do not measure a stereo implementation. Under the original separate-call implementation with held call prices, both deployed stereo rules are supersets of the original margin retries. Their dense cost floor at the original measured dispatch is already **437.10–456.15 ms** versus **347.39–367.17 ms** for direct. Even granting free retries, all policies pay the same **278.62–294.53 ms** of first-look native CPU on dense, or **32.75–32.91 ms** on weak. A resumable implementation would have different retry prices. It would still accept no 8 ms pair under the bilateral rule and retain the paired margin rule's nine dense and five weak disagreements. [Original restart timings](measurements/progressive-primary.json) · [Exact resume cost ceiling](resumable-primary-ceiling.md)

## Reproduce from metadata

The analyzer pins the two parent receipts, verifies the original decision counts, and records the per-pair oracle and frozen decisions in chronological order. Nine component and adjacent tests passed. No waveform file was opened and no benchmark ran. [Audit program](stereo_retry.py) · [Tests](../../../tests/pipeline_eval/test_stereo_retry.py)

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$release/src:$release" +  "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.stereo_retry "$fresh_output"
```
