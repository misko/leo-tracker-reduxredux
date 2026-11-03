# ALGO01: recovered GLRT evidence versus position error

The expanded reconstruction salvages most of scan 342's rejected polynomial's
observations **as two satellite tracks**. Greedy/joint recover 46 of its 48
original winning points; EM MAP recovers 45. Conservative ALGO01 retains the
36-point suffix only. Whole-scan association increases modestly, while position
error increases relative to conservative ALGO01 on both inspected scans.

## Whole-scan association and position

The denominator is the original one-winning-GLRT-mark-per-probe observation
set: **1,560 for 342 and 1,279 for 39**. Additional resolved secondary peaks
are reported separately and never divided by that denominator. Counts and
percentages below are identical in c=0 and fitted-c arms. Errors are kilometres.

| Scan | Method | Original GLRT associated | % | Additional secondary peaks | Total distinct measurements associated | Tracks | Error c=0 | Error fitted c |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 342 | Conservative ALGO01 | 1,061 / 1,560 | 68.01% | 0 | 1,061 | 42 | **1.786** | **1.736** |
| 342 | Greedy graph | 1,078 / 1,560 | 69.10% | 25 | 1,103 | 43 | 2.147 | 2.105 |
| 342 | Joint paths | 1,078 / 1,560 | 69.10% | 25 | 1,103 | 43 | 2.147 | 2.105 |
| 342 | EM MAP | 1,077 / 1,560 | 69.04% | 25 | 1,102 | 43 | 1.949 | 1.897 |
| 39 | Conservative ALGO01 | 889 / 1,279 | 69.51% | 0 | 889 | 31 | **0.760** | **0.893** |
| 39 | Greedy graph | 911 / 1,279 | 71.23% | 26 | 937 | 30 | 1.159 | 1.286 |
| 39 | Joint paths | 911 / 1,279 | 71.23% | 26 | 937 | 30 | 1.159 | 1.286 |
| 39 | EM MAP | 911 / 1,279 | 71.23% | 26 | 937 | 30 | 1.159 | 1.286 |

![Whole-scan coverage and position](coverage_and_position.png)

For 342, greedy/joint add **17 original winners plus 25 secondary peaks**
relative to ALGO01, a 1.09 percentage-point gain in original-winner coverage.
EM adds 16 winners plus 25 secondary peaks, a 1.03 percentage-point gain.
Their c=0 position errors increase by 361 m and 163 m, respectively; fitted-c
increases are 369 m and 161 m.

For 39, all three MAP variants add **22 original winners plus 26 secondary
peaks**, a 1.72 percentage-point coverage gain. The target primary curve is
one continuous 88-point track, replacing three fragments. Whole-scan track
count falls from 31 to 30 even with the new secondary curve. Error increases
by 399 m at c=0 and 393 m with fitted c.

## What is salvaged in scan 342?

| Policy | Original rejected T002 points recovered | Interpretation |
|---|---:|---|
| Conservative ALGO01 | 36 / 48 = 75.00% | Independently gated suffix; prefix remains unassigned |
| Greedy / joint | 46 / 48 = 95.83% | Two overlapping satellite curves, 65504 and 68214 |
| EM MAP | 45 / 48 = 93.75% | Same two-family structure, different ambiguous ownership |

The target-lane greedy/joint curves contain 78 total peaks and EM 77,
including surrounding winners and secondary peaks; those numbers are not
counts of the original 48-point polynomial. The common rejected points at
83.020 and 117.639 seconds remain unassociated under greedy/joint rather than
being forced through a larger residual gate. This is RF consistency evidence,
not an independent decoding of satellite identity.

## Audit protocol and scope

This audit does **not** rerun acquisition, change position estimates, choose
priors, tune gates, or run another position search. It replays each stored RF
endpoint and verifies its objective to absolute tolerance 1e-5. The earlier
causal age/disagreement phase prior and the native position nuisance model
are retained. The expanded variants replace the target-lane reconstruction;
they are not appended to the old tracks, which would duplicate observations.

At each saved endpoint it applies the existing profile RMS/bias/structure,
visibility, integer-alias and conditional-residual gates to the observations
actually retained in calibration. All retained calibration tracks pass those
gates. For fully active inputs, gate results are checked against the existing
`actual_metrics` implementation. For the conservative 342 salvage, the masked
12-point prefix is neither tested as part of the suffix nor counted as
accepted. The original nuisance design and its support are preserved.

It then reruns the existing frozen-calibration association extension across
remaining graph tracks in each scan, including eligible linear tracks. These
extensions do not vote on calibration or position. They may attach only to
satellites supported by passing curved calibration evidence. Unique original
observation identities and unique additional peak identities define coverage;
duplicate physical ownership raises an error. Association identities in the
unaffected curved lanes remain the common earlier RF nominations. There is no
new full-catalogue reassignment of every lane or discovery of all missing
graph tracks.

The historical pilot had 967/1,560 associated original points in 342. ALGO01's
1,061 total is freshly audited at the corrected endpoint: restoring 36 suffix
points alone does not explain the entire difference, because corrected
calibration also changes which frozen extensions pass. The 342 association
totals in the older failure report had explicitly not been recomputed.

GPS appears only in the reporting tool's evaluation function. It selects no
membership, endpoint or prior. There are no post-observation TLEs. Position
error comparisons preserve paired c=0/fitted-c observations and budgets;
frozen output association counts happen to be identical in both arms. More
associated evidence does not establish better localization. These two
inspected scans are not an independent generalization benchmark, and passing
finite-sample residual gates does not prove unbiased position information.

## Reproduce and inspect

For each case (`DS23-0342`, `DS23-0039`), method (`ALGO01`,
`greedy_graph_repair`, `joint_paths`, `satellite_EM`) and arm (`c0`, `fitted_c`):

```bash
PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python tools/audit_ds23_algo01_coverage.py \
  --case DS23-0342 --method ALGO01 --arm c0
```

After all 16 records exist:

```bash
PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python tools/report_ds23_algo01_coverage.py
PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 \
  .venv/bin/python -m pytest -q \
  tests/analysis/test_ds23_algo01_coverage_tool.py \
  tests/analysis/test_ds23_arc_position_tool.py
```

Nine tests pass, including safeguards against mixing winner/secondary
denominators, duplicate ownership and counting a masked prefix as part of an
accepted suffix. Ruff passes. This replay requires the earlier saved scan
inputs and endpoint artifacts referenced by each JSON's `endpoint_source`.

[Machine-readable comparison](comparison.csv) · [Validation and source hashes](validation.json)
· [Earlier conservative fix](../2026_10_18_ds23_adaptive_failures/README.md)
· [Expanded association methods](../2026_10_18_ds23_arc_variants/README.md)
· [Position propagation](../2026_10_18_ds23_arc_positions/README.md)
