# Staged 25-degree full-FOV result

The requested staged experiment completed in 19.01 seconds for five frozen
cells and the same 12 TRAIN scans. Each cell contained 774 eligible tracks,
12,958 occupied-second support units, and 17,971 observations. The catalogue
bindings cover all 12 receipts and state caches under the same conservative
regional candidate policy. All five cells lie inside the cached prior coverage.

The primary method first chose each track's ordinary unconstrained visible
Doppler winner, froze those IDs, selected one common orientation from 77,832
grid points using only their randomized training rows, and then performed one
refit among candidates that were visible under the ordinary rule, had training
cost below the unmatched cost, and remained inside the 12.5-degree half-angle
cone at every training observation. Every track remained in the capped-loss
denominator with unmatched cost one.

| cell | baseline train / held | staged train / held | supported tracks | supported occupied seconds | changed IDs |
|---|---:|---:|---:|---:|---:|
| 1 | .327 / .366 | .849 / .862 | 207 / 774 | 2,371 / 12,958 | 72 |
| 2 | .417 / .457 | .863 / .875 | 192 / 774 | 2,230 / 12,958 | 64 |
| 3 | .155 / .175 | .827 / .837 | 205 / 774 | 2,533 / 12,958 | 54 |
| 4 | .387 / .419 | .870 / .880 | 181 / 774 | 2,010 / 12,958 | 56 |
| 5 | .151 / .166 | .827 / .836 | 203 / 774 | 2,527 / 12,958 | 52 |

The constrained loss is much worse than the unconstrained baseline at every
cell. The shared-denominator invariant requires training loss to be no lower;
the held-out increase is an observed result, not a mathematical requirement.
Only 15.5%-19.5% of
occupied-second support receives a compatible candidate after the fixed-cone
refit. Supported-subset held RMS is 358-535 Hz versus baseline supported RMS
391-783 Hz, but that conditional subset statistic cannot offset the many
unmatched tracks and must not be read as an overall improvement.

The two provisional receiver mappings have identical objective values and
assignments; their yaw differs by 180 degrees because the symmetric axes can be
exchanged. Neither mapping was selected. The primary staged result provides no
support for treating a fixed 25-degree full FOV as a benign filter for this
corpus. It may still provide geographic discrimination, but any such comparison
must use the all-track capped loss rather than a retained-subset RMS.

Nine implementation tests and three independent review tests passed. They cover
the 12.5-degree threshold, 20-degree axis spacing, all-training-sample AND
compatibility, frozen baseline-before-refit order, candidate subset rules,
all-track loss monotonicity, and invariance to a 1 MHz held-row perturbation.
The executed source is hash-bound in the result. It was not reformatted after
execution and is not claimed to pass Ruff style checks.

No truth, VAL/TEST, geographic optimization, new RF, QNAP write, or production
change was used. `weight_s` is the existing pipeline's count of occupied floor-
second bins, not measured continuous duration; observation counts and summed
track spans are reported separately. Hard-cone compatibility is sampled, not a
continuous visibility proof or calibrated antenna gain.

Reproduce with the existing TRAIN caches and metadata using
`OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 .venv/bin/python
reports/2026_09_23_joint_cone_profile/staged_run.py`.
Use `staged_results.json` and its SHA256 seal for the machine-readable result.
The earlier `prototype.py` and `prototype_results.json` are preserved feasibility
work using a different simultaneous-assignment method and cone widths; they are
not the staged result. `PREEXECUTION_AMENDMENT_STAGED.json` defines the change
from the earlier protocol.
