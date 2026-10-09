# What the five-case pilot establishes

The generic retained-region recovery repaired the previously diagnosed ac11
failure, preserved the other four operational results exactly, and completed
both c arms on every pilot member. It did not achieve the 0.4 km mean-error goal.

| Pilot outcome | Fitted c | c = 0 |
|---|---:|---:|
| Baseline mean error | 11.692996 km | 11.784764 km |
| Recovery mean error | 0.762109 km | 1.381092 km |
| Improved / unchanged / regressed members | 1 / 4 / 0 | 1 / 4 / 0 |
| Recovery worst error | 1.229910 km | 1.927094 km |

All of the improvement comes from member051, the already consumed ac11
diagnostic. This is evidence that the generic implementation reproduces that
repair and behaves conservatively on four other failure-selected recordings.
It is not five independent demonstrations of improved accuracy, an unbiased
population estimate, or new independent validation.

## Controls and negative results

All five cases completed one baseline slice and one candidate slice, within
the frozen six-slice-per-phase limit. Only two single-thread numerical workers
ran concurrently. Both existing B7 publications (050 and051) have exact replay
parity in parameter vectors and objectives for both c arms. Members006,026,046
received complete new B7 baselines, including all three regional passes; their
old hard60 results were not used as the accuracy baseline.

Each member triggered one deduplicated ordinary calibration recovery. All five
calibrations qualified, but only **24 of30 recovered regional final attempts**
qualified:006 had four nonstationary attempts and046 had two. These six failures
remain in the raw receipts and the report even though the solvers returned
success. The independent convergence gate excluded them. Every original
regional candidate was preserved, and all ten selected candidate endpoints
qualified without B7 fallback. No missing member, input failure or exhausted
budget was hidden.

The numerical qualification is cheap in these cases: for example,050's prefit
and postfit polish took about0.088 and0.090 seconds, while051's took about0.124
and0.120 seconds. These figures exclude input reconstruction, association,
regional final fits and B7. Persisted nested evaluation counters are not summed
as though they were disjoint whole-pipeline costs; exact whole-job timing was
not instrumented in this pilot.

Frequency RMS is reported separately. In051 it falls136.462→83.644 Hz fitted-c
and164.956→124.767 Hz c=0. The measured position improvement comes from reference
evaluation after all fits terminated, not an inference from that frequency gain.
The other four cases have identical endpoint vectors and frequency RMS.

## Scope and next iteration

The full DS16/DS17/DS18 benchmark remains148 members (63/51/34), with the
previously verified B7 fitted-c pooled mean1.317354 km. This pilot does not
update that metric. The broader inventory contains45 newer development members;
only these five have been evaluated here. All reserves remain closed.

Next, apply the same frozen recovery rule across the complete193-member
development scope, including historical calibration failures and explicit
trigger-negative controls. Establish matched full B7 baselines for the remaining
older publications, retain every failure, and report dataset-specific means,
medians, p95, worst errors, fallbacks and paired regressions. No single repaired
case should be spliced into an otherwise unmatched cohort result.

Recovery alone is unlikely to reach0.4 km: the four unchanged pilot fitted-c
errors span0.320–1.230 km, and the historical median is0.864 km. A separate,
globally fixed likelihood-width sensitivity experiment is proposed in
[iteration106 preparation](../2026_10_09_position_error_iter106/PREPARATION.md).
It must retain matched c arms and evaluate geographic accuracy independently
of its changed likelihood. Neither experiment changes production B7 yet.

Protocol/source snapshots were pushed in8a52f5c73 before the first fit.
Independent audit verified all3078 frozen source hashes. No reference-guided
seed, satellite selection or winner selection, new RF collection, reserve
access, production change or QNAP mutation occurred.
