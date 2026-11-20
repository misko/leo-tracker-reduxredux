# Keep stock positives and rescue negative probes

Negative-only differential rescue preserved every stock winning measurement and added **401 positive probes per recording**. It recovered about 0.25 km from the unconditional differential result on DS26-0168. Stock wide still gave the closest positions on both recordings. A serial implementation that invokes the original full differential call on misses models **61.8–65.3 ms mean CPU per dual-receiver visit** on this host.

## Measured saved-IQ packets and support

The rule uses the complete stock packet on stock-positive probes. It takes the full differential packet only for stock-negative probes where the differential gate passed. Joint negatives keep stock. Neither selection nor scheduling used orbit identities, location, capture-era candidates, or future samples. Both detector parents were actually run on exactly the same complete saved IQ. The replay joins their immutable physical rows and clocks, then fits the resulting stored inputs in the same installed solver. [Prospective rule](PROTOCOL.md) · [Exact input and receiver plan](plan.json)

| Recording | Stock positive probes | Differential-only positives added | Stock positives lost in unconditional and preserved by rescue | Shared-positive winner records changed in unconditional and preserved by rescue | Added observations entering a rescue Graph track |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0168 | 4,959 | 401 | 21 | 114 | 307 |
| DS29-0604 | 3,960 | 401 | 17 | 71 | 292 |

The raw audit used all 13,545 scheduled stereo windows, retaining 15 invalid windows unchanged. Each independent differential receiver had a proposal. In 4,723 and 3,770 receiver calls where a proposal did not change the selected centers, respectively, the stock and differential full packets were exact. The rescue separately kept every original stock winner regardless of proposal. In unconditional tracking preparation, 50 and 27 of the shared winners had different CFO values. The fusion retained those original CFO values and all other original winning measurements. [Complete probe audit](probe-audit.json) · [Installed Graph audit](graph-support.csv)

Downstream tracking still reorganized when added observations entered. Compared with stock, each rescue lost 57 original points from Graph tracks while gaining 354 assigned points net on DS26-0168 and 352 on DS29-0604. Counts of prepared tracks were 142 → 155 and 102 → 122. The original measurements remained in the tracker input on both recordings. [Graph support](graph-support.csv)

## Position and conditional frequency

Both arms published in every method. Each slash gives `c = 0` / fitted `c`. The four original v5 options use archived capture-era factors and remain historical comparisons. [All coordinates, RF and target checks](scores.csv) · [Four original v5 options](capture-era-v5.csv)

| Recording | Input | Position error (km) | Conditional RF RMS (Hz) |
| --- | --- | ---: | ---: |
| DS26-0168 | Stock wide | 0.805 / 0.796 | 70.86 / 70.87 |
| DS26-0168 | Unconditional differential | 1.724 / 1.722 | 84.76 / 84.76 |
| DS26-0168 | Negative-only rescue | 1.472 / 1.473 | 84.44 / 84.44 |
| DS26-0168 | Original v5 baseline | 1.515 / 1.551 | |
| DS29-0604 | Stock wide | 0.735 / 0.734 | 95.52 / 95.48 |
| DS29-0604 | Unconditional differential | 0.760 / 0.775 | 98.64 / 98.59 |
| DS29-0604 | Negative-only rescue | 0.780 / 0.797 | 96.93 / 96.91 |
| DS29-0604 | Original v5 baseline | 0.982 / 1.041 | |

Rescue met the original baseline v5 error and the within-10% target for 2/2 recordings in each arm. Stock wide also met both counts. Unconditional differential met each count on 1/2. On DS29-0604, rescue reduced conditional RMS from unconditional while increasing both position errors. All four historical options are shown alongside the three new-era methods in each chart. [`c = 0` position chart](charts/c0/whole-iq-negative-rescue.png) · [Fitted `c` position chart](charts/fitted_c/whole-iq-negative-rescue.png)

## Detector work and actual position resources

An online version can skip the second dual-RX call only when both stock probes are positive. The model uses the measured stock and differential CPU and wall clocks on precisely the same saved visits. It adds one complete differential call for each miss visit and the measured host selection cost. The serial wall estimates exclude scheduling, buffering, and position time. No specialized second-pass kernel or online mixed-stream timing was measured. [Sealed raw-call ledger](raw-clock-ledger.jsonl.gz) · [Online workload model](online-work.csv)

| Recording | Second calls | Stock measured / unconditional measured / rescue modeled CPU mean (ms) | Rescue modeled serial wall mean (ms) | Stock measured / unconditional measured / rescue modeled calls within 20 ms |
| --- | ---: | ---: | ---: | ---: |
| DS26-0168 | 4,990 / 6,774 (73.7%) | 24.80 / 51.27 / 61.81 | 64.79 | 248 / 0 / 6 |
| DS29-0604 | 5,664 / 6,756 (83.8%) | 23.85 / 49.90 / 65.28 | 68.56 | 562 / 0 / 15 |

The two fresh rescue position services took 112.39 and 77.79 CPU s, with measured wall time 113.19 and 78.57 s. They used pinned single cores, a 512 MiB cgroup with zero swap, and a 210 s deadline. The highest cgroup charge was 472.25 MiB, with zero OOMs. These timings start at stored native factors. [Position resource receipts](resources.csv) · [Prediction seal](prediction-lock.json)

An initial preflight treated the original request digest as a request object and stopped before fitting. The corrected check uses the sealed digest and independently authenticates the complete rebound request. After the rescue sealed, the parent report writer acquired a new source digest. A fresh raw audit reproduced every sealed probe decision and timing row before geographic scoring. [Source audit](source-audit.json) · [Score seal](score-lock.json)
