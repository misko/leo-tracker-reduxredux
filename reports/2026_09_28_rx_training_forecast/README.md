# Grouped training partitions and satellite forecasts

**The grouped partitions and training-only satellite forecast bank are complete for all ten recordings.** The independent audit found zero cross-role source overlap and verified every forecast destination. This completes the first two prerequisites for a receiver detection-order test; it does not yet evaluate a lag model, increase satellite-identification confidence, or measure localization accuracy.

## Partitions completed

| Temporal role | Recorded paired windows | Permitted use |
|---|---:|---|
| Training prefix (first 60% of time) | 13,291 | Reconstruct tracks, select satellite candidates and fit CFO |
| Reception period (next 20%) | 4,430 | Future reception-conditioning observations |
| Frequency-target period (last 20%) | 4,433 | Future frequency-scoring observations |
| Boundary embargo | 1 | Excluded |
| **Total** | **22,155** | Both receivers remain together |

These are fractions of recording time, not an outcome-selected fraction of detections. Candidate absence does not remove a recorded opportunity. All 22,155 connected groups happen to contain one paired probe window in this corpus; overlapping observations from different tracks remain inside that group.

The independent audit checks the actual source intervals rather than trusting the partition generator's summary. It finds **zero cross-role overlap** for recorded windows, all 81,390 projected candidate supports, and all 25,323 legacy associated observations. The original 1,421 training–held overlapping interval pairs are now entirely within one role: 971 in training, 265 in reception, and 185 in frequency targets. Removing every candidate list and regenerating the partitions also leaves every window and group assignment unchanged.

The separate six-record calibration/four-record evaluation assignment covers 10, 5 and 2.5 MHz in both sets. The single 7.5 MHz recording stays in calibration. Every recording, including coefficient-evaluation recordings, may condition its target hypothesis on its initial Doppler-training prefix; that is separate from fitting shared reception coefficients. These reused recordings are not blind confirmation.

## Forecast construction

| Completed forecast pilot | Result |
|---|---:|
| Recordings completed | 10 / 10 |
| Tracks reconstructed from training prefixes | 511 |
| Tracks retained under the frozen three-per-recording cap | 30 |
| Causal catalogue size, depending on snapshot | 11,116–11,119 |
| Future reception/frequency windows covered | 8,863 |
| Candidate × track × window forecasts | 79,767 |
| Minimum probability mass retained by a top-three shortlist | 86.62% |
| Median retained probability mass | 100% to displayed precision |

The other 481 reconstructed tracks were outside the predeclared cap, not rejected after inspecting future detections. Retained mass is a calculation under the fixed training likelihood and reference-conditioned catalogue; it is not calibrated satellite-identification confidence. Each shortlist also has separately normalized conditional probabilities summing to one.

The completed run exited 0 in **226.04 seconds**, with **535,024 KiB peak RSS**. It stayed inside the original five-minute numerical limit. All ten recordings, all 30 selected tracks and all 79,767 forecasts passed the coordinator's audit and an independent Terra review. The first invocation failed before ranking on a public-API mask constraint; its evidence is retained and the corrected launch was explicitly frozen.

The candidate-bank adapter filters raw probes to training windows before public candidate projection or track reconstruction. It selects at most three qualifying tracks per recording, ordered by latest training endpoint and then track ID. It searches the eligible causal catalogue in fixed batches of 512, using training-time visibility only, a constant CFO fitted to all prefix observations, fixed sigma=100 Hz, and the known diagnostic roof point.

Historical candidate identities, probabilities and residuals are not input to the new search. A sanitized snapshot-authority file carries only input/analysis hashes, snapshot digest and reference-site binding. The forecast destinations come from partition metadata alone. The bank exports the top three candidates' normalized-frequency predictions, visibility and ENU line-of-sight at exact future window midpoints. Conditional top-three probabilities are distinct from the probability mass retained from the full eligible catalogue.

The installed predictor requires a mixed internal mask. Those structural masks are retained only to satisfy its interface; the explicit training-ranking routine uses every observation in each prefix-built track. Prediction-only future inputs have placeholder measurements and a structural mask, neither of which is scored. The [integration amendment](BANK-LAUNCH-AMENDMENT.md) records the failed first invocation and correction before satellite ranking.

## Remaining requirement for detection-order testing

The forecasts are in normalized track-frequency coordinates. Raw GLRT candidates use receiver/channel-specific CFO and ambiguity branches. A training-derived alias, RF-scaling and receiver-offset mapping must connect those coordinates before evaluating which receiver detected a candidate first. The current bank explicitly marks raw-candidate matching unavailable; no evaluation detections were used to choose an alias or offset.

After that mapping is fixed, reception evidence from the middle period can update candidate confidence and the final period can test held-frequency prediction. Compare against Doppler-only and static receiver geometry with correlated noise, retaining receiver-swap and trajectory-reversal controls. Track caps, reused data, unsurveyed/reference-conditioned coordinates and provisional beam calibration remain limits on interpretation.

## Reproduction

- [Frozen protocol](PROTOCOL.md), [partition artifact](partitions.json), [partition launch](partition-launch.json), [partition resources](partition-resources.txt).
- [Independent partition audit](partition-audit.json), [audit script](audit_partitions.py), [outcome-removal audit](outcome-removal-audit.json).
- [Snapshot authority](snapshot-authority.json), [installed runtime binding](runtime-binding.json).
- [Completed candidate bank](candidate-bank.json), [forecast audit](bank-audit.json), [forecast audit script](audit_bank.py).
- [Corrected bank launch](bank-corrected-launch.json), [resource receipt](bank-corrected-resources.txt), [exit status](bank-corrected-exit-code.txt).
- [Original failed launch](bank-launch.json), [original traceback](bank-terminal.log), [integration amendment](BANK-LAUNCH-AMENDMENT.md).
- [Partition builder](../../tools/rx_grouped_partitions.py), [candidate-bank builder](../../tools/rx_training_candidate_bank.py).
- [Partition tests](../../tests/research/test_rx_grouped_partitions.py), [candidate-bank tests](../../tests/research/test_rx_training_candidate_bank.py).

Partition generation completed in 2.10 seconds with 541,876 KiB peak RSS. Fourteen focused tests, including installed prediction-contract integration, passed; Ruff passed. Each real stage is limited to one numerical thread, nice 19, 4 GiB address space and 300 seconds. No raw IQ, RF collection, QNAP modification or position search is involved.
