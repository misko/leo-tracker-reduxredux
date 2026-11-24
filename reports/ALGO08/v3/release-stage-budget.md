# How much faster the receiver must get for a 2× DS30 result

On the frozen 100-recording ALGO08v3 release panel, **93 of the 95 runs with a terminal timestamp spent more than half their elapsed time reaching the saved detections**. Across those 95 runs, reaching detections took **6,778 s**, or **67.9%** of the 9,984 s total. Everything after detection publication took 3,206 s. The other five runs exited with solver errors. Their 430 s are included in the timing gates below. The measurements come from existing benchmark receipts and output timestamps. This analysis ran zero receiver or solver jobs. [Historical release and assigned cases](https://github.com/misko/leo-tracker-reduxredux/blob/2424d8897e6003f39550e2ae50ba3cd149da389a/reports/ALGO08/v3/ds30-100/README.md) · [Recording-level timing evidence](https://github.com/misko/leo-tracker-reduxredux/blob/a9e768bc040efcfe382a131e9e86e46f24ceb916/reports/ALGO08/v3/measurements/release-stage-budget.json)

![Historical share of elapsed time before detections and required speedups across the two stages](development/release-stage-budget.png)

### Two timing gates

Both the median of paired candidate-to-v3 time ratios and the ratio of summed times must be at most 0.5. The table scales the two observed intervals by separate fixed factors and finds the least speedup before detections that meets both gates. The range allows each unpartitioned failure to have spent its entire runtime in either interval. This retains the original 100 denominators. It assumes both intervals scale uniformly across recordings and that fix decisions remain unchanged.

| Assumed speedup after detection publication | Required speedup from startup to detection publication |
|---:|---:|
| 1.00× | 3.60–4.31× |
| 1.25× | 2.73–2.95× |
| 1.50× | **2.35–2.44×** |
| 1.60× | 2.25–2.31× |
| 2.00× | 2.00× |

Even making the entire interval after detections instantaneous gives at most **1.46× on the paired median and 1.54× on the summed gate**. Conversely, work before detections includes launch, file access, verification and publication of the native packet as well as the two-scan detector. A 2.4× improvement to a detector kernel alone would save only its share of this interval.

### Single-core CPU and file residency

The historical processes spent **73.6% of summed elapsed time on CPU**. If each process used half as much CPU and its remaining elapsed time stayed constant, the paired median and summed elapsed speedups would both be **1.58×**. Under this assumption a **3.12× reduction in CPU time** would meet both elapsed gates. Elapsed time outside CPU can include scheduler delays and input waits. Streaming or changing the access pattern can affect both components.

| Original payload pages resident at launch | Runs with both timestamps | Fraction of summed elapsed time before detections |
|---|---:|---:|
| At most 1% | 49 | 70.5% |
| Between 1% and 99% | 25 | 69.2% |
| At least 99% | 21 | 55.7% |

The groups contain different recordings. For example, on median-sized DS30-0004 the installed process reached detections in 83.645 s and exited in 126.979 s. Its target at half that observed elapsed time is 63.489 s. The newer DS30-0004 study times only a solver starting from the saved native packet. All of these recordings came from one site. [DS30-0004 saved solver comparison](https://github.com/misko/leo-tracker-reduxredux/blob/a9e768bc040efcfe382a131e9e86e46f24ceb916/reports/ALGO08/v3/nomination-handoff.md)

### Reproduction and limits

The release decision binds all 100 archived pair receipts by SHA-256. For the 95 with terminals we subtracted the detection-to-terminal modification-time interval from the launch-to-terminal clock stored by the original timing harness. All 52 corresponding rows in the first published timing table matched within a microsecond. No detection or terminal body needed reading. The release receipts bind the clocks and case identities. File timestamps for the 43 additional terminal cases came from the retained benchmark directories and depend on those directories preserving mtimes. Errors, full-wall totals, CPU totals, and both timing gates are kept separately in the receipt. [Earlier timing table](https://github.com/misko/leo-tracker-reduxredux/blob/a9e768bc040efcfe382a131e9e86e46f24ceb916/reports/ALGO08/v3/first-55/stage-clocks.csv) · [Reconstruction and gate calculation](https://github.com/misko/leo-tracker-reduxredux/blob/a9e768bc040efcfe382a131e9e86e46f24ceb916/reports/ALGO08/v3/release_stage_budget.py)

Run the script with the original Gauss panel directory, the linked release's `decision.json`, the earlier `stage-clocks.csv`, and an output JSON path. Pass `--plot FILE.png` for the figure. Both small input ledgers are checked against their published digests before any panel measurement is used.
