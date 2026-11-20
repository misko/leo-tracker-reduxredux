# Three-lag pilot timing through two complete saved-IQ positions

The three-lag scout restored **67 of 237** original physical winners that both earlier detectors missed on DS26-0197 and **73 of 214** on DS29-0519. It produced both calibration arms on both recordings. It did not improve on the best earlier detector on either recording, and no three-lag position met the 5% or 10% original-v5 allowance. [Zero-calibration chart](charts/c0/modifications.pdf) · [Fitted-calibration chart](charts/fitted_c/modifications.pdf) · [All four original v5 policies and paired results](scores.csv)

## Position and conditional frequency fit

Every pair below is `c = 0` / fitted `c`. The methods share each recording's original supplied 25 km offer, causal TLE snapshots, track settings, installed compact receiver and geographic evaluation reference. Each fit uses its method's actual complete observed factors. DS26-0197 is the known hard case. DS29-0519 was fixed before these replays as the control from the earlier archived pilot census. [Protocol](PROTOCOL.md) · [Matched input and release hashes](source-lock.json)

| Recording | Original v5 no-repair error | Four centers | Released fifth center | Three-lag fifth center | Three-lag conditional RMS |
|---|---:|---:|---:|---:|---:|
| DS26-0197 | 0.528 / 0.689 km | 0.792 / 0.992 km | 0.759 / 0.937 km | **0.891 / 1.034 km** | 86.641 / 86.687 Hz |
| DS29-0519 | 0.248 / 0.319 km | 0.334 / 0.324 km | 0.665 / 0.763 km | **0.420 / 0.538 km** | 92.656 / 92.665 Hz |

Four centers met both allowances on one of two fitted-arm cases. Released fifth and three-lag fifth met neither allowance on either arm. Fitting `c` raised the three-lag geographic errors by 0.143 and 0.118 km. Its conditional fit RMS rose by 0.046 and 0.008 Hz. Those frequency values describe the observations selected by that same detector. [Per-arm summary](summary.json)

## Complete waveform and resource receipts

Both replayed every eligible saved visit on both receivers and used only their measured native candidates for positioning. The new scout added 1,019 and 872 gated candidate records relative to released fifth. Within the complete original-winning probe roster it gained 68 and 75 physical matches, losing seven and ten existing matches. Those different observation sets produced worse fixes than the best earlier detector here. [Per-recording pilot overlap](probe-audit.json) · [Earlier matched-window detector study](../multilag-search/README.md)

| Three-lag saved-IQ replay | Detector calls ≤20 ms | Raw wall | Position wall | Complete worker wall | Charged peak / swap |
|---|---:|---:|---:|---:|---:|
| DS26-0197 | 0 / 6,761 | 134.50 s | 54.92 s | 190.27 s | 512 MiB / 0 |
| DS29-0519 | 2 / 6,727 | 118.81 s | 55.20 s | 174.95 s | 512 MiB / 0 |

The two new services ran serially with a 540 s deadline and used CPU4/5 with reversed lane assignments on DS29. Each stayed in the charged-memory cap and recorded zero swap or OOM kills. Complete candidate dual-call wall p50/p95 was 26.57/39.90 ms on DS26 and 25.86/37.00 ms on DS29. Historical controls ran in their own scheduling intervals and CPU placements. The same-core timing experiment in the detector study measures the isolated scout cost. [Runtime table](timing.csv) · [Candidate resource receipts](resources.json)

DS29's standard service supervisor initially rejected its terminal receipt because Linux lists the entry CPU set in sorted order and the raw worker plan orders the lanes as 5 then 4. The report reconciler authenticated the same successful systemd invocation against its launch, cgroup, exact CPU set and both lane receipts. It retained the actual sorted entry receipt and original lane order. No rerun or replacement estimate was used. [DS29 terminal receipt](receipts/DS29-0519/service.json) · [Prediction seal](prediction-lock.json)
