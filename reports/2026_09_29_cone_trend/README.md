# Scan-consistent cones with an explicit trend alternative

**All four frozen width arms are complete; 70/72 selected numerical audits pass.** No width is promoted as a reliable sub-km solution. Every complete DS7 and DS8 median remains above 1 km, and the late DS9 eight-scan error worsens versus the no-cone trend model in every arm.

This model conserves total prior mass when cone compatibility decreases: satellite mass transfers to the unassociated trend. Shared axes and widths apply throughout each scan set. The edge is soft, held geometry is audited separately, and cross-RX satellite identity remains unverified.

The 20° arm worsens held prediction in 17/18 panels and reduces nominal sub-km sets from three to two. The 50° arm improves held prediction in 14/17 audited panels, but location changes are small and its late DS9 error remains 3.698 km. Predictive gains are not sufficient evidence of geographic gains. Nominal/swapped/co-pointed controls are scored at the nominal fit without refitting and do not establish calibrated orientation or travel direction.

| Half-angle | Status | Selected audits | Lower location error | Better held prediction |
|---:|---|---:|---:|---:|
| 20° | [Complete](RESULTS-c20.md) | 18/18 | 8/18 | 1/18 |
| 30° | [Complete](RESULTS-c30.md) | 17/18 | 8/17 | 8/17 |
| 40° | [Complete](RESULTS-c40.md) | 18/18 | 11/18 | 10/18 |
| 50° | [Complete](RESULTS-c50.md) | 17/18 | 10/17 | 14/17 |

Across the dependent width/panel combinations, location improves in 37/70 audited results and held prediction in 33/70. These counts are descriptive sensitivity outcomes, not independent trials or a rule for selecting width. Each receiver keeps one axis and half-angle throughout the scan set; each candidate keeps its trajectory. Half-angle is measured from the receiver axis, distinct from the assumed 20° axis separation.

## Eight-scan median error

Metres; each median requires all three early/middle/late block audits. Four-scan medians and every individual outcome remain in the arm reports.

| Model | DS7 | DS8 | DS9 | Late DS9 eight-scan error |
|---|---:|---:|---:|---:|
| No-cone trend mixture | 2,024 | 1,721 | 876 | 3,681 |
| 20° | 2,131 | 1,652 | 1,463 | 4,266 |
| 30° | 2,109 | Incomplete | 683 | 3,960 |
| 40° | 2,014 | 1,693 | 717 | 3,723 |
| 50° | Incomplete | 1,725 | 832 | 3,698 |

## Geometric consistency and the broader comparison

The model has shared geometry but does not enforce hard visibility. Across audited panels, the fraction of satellite posterior weight inside the nominal cone throughout training ranges from 11.24–19.78% at 20°, 39.44–61.55% at 30°, 84.76–95.09% at 40°, and 94.80–99.72% at 50°. Broader compatibility has not produced reliable short-set location estimates. Held geometry is audited separately; the likelihood does not model reception/non-reception or verify shared satellite identity across RX tracks.

[The matched comparison of twenty completed approaches](MODEL-COMPARISON.md) includes median errors by dataset and scan-set size, source audit status, worst-panel errors and a descriptive ranking. The inherited search center is already 809 m from the exposed unsurveyed reference; nominal sub-km counts alone do not demonstrate radio-derived information gain or blind accuracy. No optimizer start or width is selected by reference error.

[The hard-cone follow-up proposal](NEXT-HARD-CONE.md) distinguishes a complete satellite explanation from a mixture that assigns unsupported tracks to background. The next check is whether any position/timing choice inside the existing search domain can rescue hard support, before attempting discontinuous hard-cone fits. Receiver world pose, cable mapping, beam shape and candidate-bank completeness remain assumptions requiring separate evidence.

## Verification and retained failures

281/288 starts qualify; all 360 child processes exit zero. The selected audits fail for **DS8_late_8_c30** and **DS7_middle_8_c50** because timing finite-difference stencils cross interpolation nodes and exceed the frozen derivative-discrepancy limit. Their estimates remain visible but unvalidated, and their affected medians remain incomplete. No completed fit was retried or substituted after an audit failure.

Every arm verifies frozen sources and inputs, reconstructs training-based selections, checks all coordinates at two finite-difference steps, and replays the no-cone model at selected points. Nine synthetic tests passed before the experiment. Total child wall time is 3,877.37 s across separately published batches; maximum child time is 33.08 s and peak RSS 668,804 KiB. One bounded scientific worker used cached data; no RF collection, raw-waveform reads, propagation or provider fetches were performed.

[Protocol](PROTOCOL.md), [frozen plan](plan.json), [nine prelaunch tests](tests.log), [source/input seal](input-seal.json).
