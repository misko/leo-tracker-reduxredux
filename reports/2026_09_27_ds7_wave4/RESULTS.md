# DS7 coverage expansion: second chronological group

All four predeclared methods achieve sub-kilometre error on `group8-02`.
This extends validated evaluation coverage to 24 of 88 recordings and three
of eleven chronological groups. It does not establish full-DS7 accuracy.

| Frozen method | Group 1 | Group 2 (new) | Group 11 |
|---|---:|---:|---:|
| Equal independent-position mean | 1,930.07 m | **628.67 m** | **443.02 m** |
| Inverse training-RMS-squared mean | 2,152.44 m | **601.07 m** | **602.41 m** |
| Mean of lowest-RMS 75% | 2,532.71 m | **836.50 m** | **446.91 m** |
| Joint static-site Doppler fit | 2,541.48 m | **887.79 m** | 1,322.09 m |

Group 2 was selected by the next missing chronological partition before its
predictions or scores. All eight singles and the joint fit converged with
interior solutions, covering 469 eligible tracks with no exclusions. None of
the eight new singles was below 1 km. Across the 24 distinct tested singles,
only two are below 1 km. Combining recordings helps on this group, but neither
convergence nor low training RMS establishes individual location accuracy.

The three controls use the same eight qualified independent fits. The frozen
75% rule keeps six by training RMS; no member or weight was chosen from
geographic error. Equal averaging and each RMS control are below 1 km on two
of the three tested groups; the joint fit is below 1 km on one. These counts
are not independent population estimates or a reliable model ranking.

Evidence: [joint and final-single scores](coordinator/group02-completion-score-v1/scores.json),
[equal mean](coordinator/controls-equal-group02-score-v1/scores.json),
[inverse RMS](coordinator/controls-inverse_rms2-group02-score-v1/scores.json),
[lowest RMS 75%](coordinator/controls-lowest_rms75-group02-score-v1/scores.json),
[exact source linkage](coordinator/controls-group02-source-audit.json).
Earlier groups are recorded in [wave 3](../2026_09_27_ds7_wave3/RESULTS.md).

## Preparation and computation

The serialized combined-export controller completed all eight captures in
589.885 seconds, below its 1,200-second deadline. Per-recording reported times
sum to 567.297 seconds; these omit controller overhead. There were no timeouts
or retries. All 72 prepared artifact hashes, all 88 source identities and the
exact preservation of the earlier 16 ready records passed the
[independent input audit](review/INPUT-INTEGRITY.md).

The new scientific panel used 382.778 of its 900 adapter seconds. The joint
fit used 248.331 seconds of its 300-second limit. No new RF or raw IQ was used.
The final frozen input is
[24-ready input](inputs/inputs-first16-group8-02-ready-v1.json).
At this wave's closeout, 64 recordings remain unprepared in that snapshot.
The separately bounded wave-5 preparation continues chronological captures
017–024; its later readiness does not retroactively change this sealed wave.

## Exact computational improvement

Profiling found stationary-offset fitting consumed about 90% of objective
time. A new optional batched objective preserves the existing kernel, candidate
order and per-document summation order. Comparisons against the active fast
objective matched objective and gradient exactly on frozen 1/2/4/8 inputs.
Incorrectly labeled out-of-domain probes and an earlier scalar comparator are
retained and explicitly superseded in the [benchmark report](batched-objective/README.md).

The optional adapter passed a separately predeclared full first-eight fit:
its response bytes match the frozen response exactly, including parameters,
training likelihood, RMS, convergence, boundary flags and evaluation counts.
It took 144.968 adapter seconds and peaked at 639,140 KiB. The earlier frozen
fit took 170.304 seconds under different load; this is not a controlled speed
ratio. [Comparison receipt](batched-objective/fit-validation-comparison.json).
The new adapter was not used to produce the group-2 scores above.

Full88 joint execution still needs a measured memory/resource solution:
the current retained-array estimate exceeds the 4 GiB envelope. The pooled
independent-position controls remain feasible once all singles are available.
[Full88 readiness review](solver/FULL88-READINESS.md).

## Clock prerequisite and verification

A separate review identified missing boundary and condition-number checks in
the synthetic clock qualification. A new audit version enforces them; all
three existing synthetic cases still pass. This does not establish hardware
clock topology, physical drift bounds, or admit a calibrated real-data model.
[Clock review](clock-review/REVIEW.md) and
[corrected qualification](clock-review/qualification-audit-v2.json).

All 91 relevant tests and Ruff pass. The earlier wave-3 closeout's 267 bindings
remain unchanged. This corpus uses one exposed site and an unsurveyed operator
reference. The full88 estimate has not run, and the full-DS7 goal remains open.
