# Longest missing-segment investigation

This read-only investigation uses the same frozen 300-second DS9 recording,
maintained server segmentation, and physical PLUTO+ curvature-v8 A250 output.
It excludes the nine references represented through longer merged outputs and
ranks the remaining 17 references by support duration. No detector or tracker
configuration, golden fixture, or published result was changed.

## Important correction: reference 10 is not established ARM failure

The user correctly questioned the server assignments. At approximately 53 s,
server reference 10 starts following a different branch. ARM output 0 instead
continues smoothly onto the points the server labels reference 16. Treating
reference 10 as ground truth incorrectly penalizes this ARM continuation.

An unweighted quadratic fitted only to reference-10 observations before the
divergence predicts the subsequent reference-16 branch much more accurately:

| Fit interval | Fit RMS | Fitted acceleration | Future ref 10 RMS | Future ref 16 RMS |
|---|---:|---:|---:|---:|
| 36–48 s | 48.7 Hz | −29.2 Hz/s² | 5391.6 Hz | 153.4 Hz |
| 38–50 s | 49.6 Hz | −30.6 Hz/s² | 5537.0 Hz | 227.6 Hz |
| 40–52 s | 61.3 Hz | −35.8 Hz/s² | 6029.9 Hz | 674.2 Hz |

Future evaluation uses 53–61.5 s, nine reference-10 points and 21 reference-16
points. These are diagnostic windows selected after inspecting the disagreement,
not a prospective validation dataset. All three support the same conclusion.
The reference-10 tail departs by roughly 7.8 kHz at its end from the earliest
continuation. ARM follows reference 16 closely. This is strong evidence for a
server grouping error, although CFO continuity alone does not prove satellite
identity. The underlying detections can be real while their track assignment
is wrong. We have not instrumented the server's Hough selection to establish
exactly which selection decision caused the switch.

The previous description of reference 10 as an ARM mixing error is withdrawn.
The frozen 46/63 membership result remains reproducible **agreement with server
segmentation**, not a physical track recovery accuracy estimate. No threshold
was relaxed and no reference label was rewritten to improve that count.

See [branch close-up](ref10-branch.png) and
[three-window measurements](ref10-continuation.json).

## Longest discrepancies

| Reference | Channel/RX | Duration | Matching ARM input / server points | Best ARM output coverage | Finding |
|---|---|---:|---:|---:|---|
| 2 | 4/1 | 50.11 s | 68/84 | 67/84 (79.8%) | Almost recovered; one point below the 80% threshold. Sixteen source windows lack passing ARM candidates. The remaining unassigned matching point is at 2.295 s, before a 7.116 s gap in matching reference detections; tracker gap limit is 4 s. |
| 10 | 1/0 | 37.14 s | 69/69 | 60/69 (87.0%) | Fails source purity (74.1%), but the server tail is likely misassigned; ARM follows the smooth continuation. |
| 30 | 2/1 | 34.38 s | 28/40 | 28/40 (70.0%) | All matching input points recovered. Twelve missing input windows prevent 80% reference coverage. Four additional ARM output sources lie near the same curve. |
| 8 | 3/1 | 32.23 s | 10/42 | 5/42 (11.9%) | Severe input loss; only ten matching points remain, with 18.68 s and 5.73 s gaps. Output retains a late fragment. |
| 34 | 1/1 | 32.13 s | 35/45 | 32/45 (71.1%) | Nine windows have no ARM candidate; one has incompatible CFO. Matching input also has a 6.58 s gap. |
| 47 | 2/0 | 30.60 s | 9/24 | 0/24 | Both input loss and seed starvation: nine compatible seeds exist but none survive the cap; best rank 1045 versus cap 512. |

The raw ARM detector receipts narrow the upstream losses further. All retained
coarse peaks were screened out in 14/16 missing windows for ref 2, 11/12 for
ref 30, all 32 missing windows for ref 8, nine windows for ref 34, and 14/15 for
ref 47. Remaining absent windows in refs 2/30/47 have serialized candidates
but all margins below 0.025. Ref 34's other lost point has a passing candidate
at an incompatible CFO. This identifies the stage where evidence disappears;
it does not establish that disabling the coarse gate alone would yield a
correct passing GLRT result. No raw-IQ counterfactual was run here.

Seed selection is independently reproduced against the frozen ARM counters.
Refs 19 (22.83 s), 59 (20.37 s), and 33 (18.45 s) have 21/23, 35/35, and 27/30
matching input points, respectively, but no compatible retained seed. Their
best compatible ranks are 975, 549, and 623. These are cleaner targets for a
seed-selection correction than the longer detection-limited references.
Refs 2/10/30/8/34 have 43/87/13/6/50 compatible retained seeds; seed starvation
does not explain those discrepancies. See [independent seed audit](arm-seed-audit/README.md).

## Evidence and reproduction

- [All 17 source-level diagnoses](diagnosis.json) contain candidate availability,
  CFO residuals, output assignments, raw gate counters, and gap intervals.
- [Six longest close-ups](longest-six.png) show actual points. Interpolated
  residuals are visual diagnostics, not the membership decision rule.
- [Input hashes](input-hashes.json) bind all 139 ARM raw receipt batches,
  projected inputs, source maps, track files, thresholds, and audit script.
- Run `../diagnose_missing.py` and `../inspect_ref10.py` using Python with
  NumPy/Matplotlib. The seed audit has its own reproduction command and manifest.

The next correctness work should distinguish physical-continuity disagreements
from actual lost evidence: inspect server branch assignments before scoring
them as failures; replay selected coarse-gated windows against the full search;
then test seed coverage on refs 19/59/33. This investigation does not promote a
new tracker or claim an improved physical recovery rate.
