# Can the DS30-0255 history-route fallback start earlier?

The first proven rejection in DS30-0255 is a failed predictive track in the
**fitted-`c` repair refit**. Replaying the fitted arm first would skip the
fixed-zero repair refit. The entire two-arm refit took **0.908 CPU s**, while
the route with guarded nomination reuse remained **5.473 CPU s** slower than
the fresh named worker. Even a free refit would leave **4.565 CPU s** to
recover. This investigation replays the saved gate evidence and starts no
new solver or receiver worker. [Original enrolled holdout](unseen-saved-holdout-0255.md) ·
[Measured nomination handoff](nomination-handoff-0255.md)

## When the rejection becomes available

| DS30-0255 scope inside the measured handoff worker | CPU s | Wall s |
| --- | ---: | ---: |
| Cold nomination, all three scheduled branches | 11.516 | 11.561 |
| Initial curved gate | 1.027 | 1.027 |
| Salvage | 2.608 | 2.608 |
| Provisional salvage seed gate and eligibility check | 0.483 | 0.483 |
| Predictive selection | 0.512 | 0.512 |
| Original joint finish | 1.329 | 1.329 |
| Repair admission and preparation | 0.260 | 0.260 |
| Both repair fits | 0.908 | 0.908 |
| First lean attempt through refusal, inclusive | **18.646** | **18.691** |
| Subsequent named fallback through numerical evidence | **30.995** | **31.026** |

The healthy earlier-orbit census selects lean. The cold score gap decides
whether to finish the other nominations, using a score from the cold
calibration model. The curved support screen then keeps **3,402 of 5,226**
rows. Salvage restores **1,137** and the following screen keeps **3,794**.
The provisional salvage eligibility check starts no fits.
Those states precede the original joint fits and the repair cap applies to
their later common subset. Using the initial lost-row fraction as the cap
would change its denominator and omit salvage.

The initial fixed-zero and fitted fits reject three and two curved tracks
respectively and pass all **660** predictive observations. The repair needs
both rejection lists and both fit states to form a common mask and seed the
refits. Its proposed removals, **151 of 3,794 curved rows, 10 of 660
predictive rows, and four of 114 tracks**, satisfy the original 5% limits.
The proposal also has two receivers, 20 families, 3,400 residual degrees of
freedom, and both initial points inside the offered region.

Both repaired endpoints and phase convergence checks pass. Both arms pass
all **3,643** retained curved observations. The fitted arm fails exactly one
17-observation predictive track, which passes in the original fitted fit and
the repaired fixed-zero fit. The predictive decision depends on residual
RMS, bias, alias, whitened noise and visibility at the refitted state. The
archived gate exposes the failing track and its point count. Its diagnostic
does not retain which scalar test failed. The tracks, caps, cold score and
initial fits provide no sufficient earlier failure certificate here.
[Original finish and chronology](blind_joint_finish.py) ·
[Repair masks, caps and refits](blind_joint_repair.py)

## Controls for candidate redirects

| Frozen observable or gate | DS30-0255 | Accepted archive control |
| --- | --- | --- |
| Cold nomination gap ambiguity | Ambiguous and later falls back | North simulation was also ambiguous and its original paired fit passed |
| Original joint gate rejects | Both arms reject curved support | DS30-0169 rejects a 30-observation curved track in both arms, then repairs successfully |
| Fitted arm fails the final repair gate | Predictive 633 of 650, decline the repair | DS30-0169 passes 454 of 454 in each arm, keeps both refits and their original published order |

The prototype calls the existing calibration-symmetric gate on the fitted
result and stops if its term of the conjunction fails. The replay visits
one completed arm record on 0255 and both on 0169, reproducing both
original repair decisions. The 0169 comparison is physical, using the
original signed 20 ms observations and its original 25 km offer. It
reproduced the named publication previously in **12.065 s**, against
**17.893 s** for the archived named worker. The North check uses separately
published simulation evidence. The earlier constrained-rescue study applies
a similar short circuit to a different pair of fits.
[DS30-0169 comparison](history-risk-held-0169.md) ·
[North comparison](history-risk-raw.md) ·
[Earlier constrained-rescue veto](constrained_pair_veto.py)

The prototype verifies the acceptance logic for completed records. Changing
live arm order or omitting an arm also changes which private diagnostics
and potential numerical exceptions are observed. The study does not certify
those behaviors or exercise the prototype in the production route.

## Break-even boundary

The observed deficit after guarded reuse is **5.511 wall / 5.473 CPU s**
against **50.721 wall / 50.666 CPU s** for installed v3. In the measured
handoff child, an instant redirect immediately after cold nomination could
at most avoid **7.130 CPU s**, or **6.102 CPU s** immediately after the
initial curved gate. After salvage the remaining lean work falls to
**3.494 CPU s**, including every later gate and the provisional
salvage eligibility check. This upper bound grants the entire remaining lean
scope, zero decision overhead and unchanged named fallback costs. A
break-even refusal could spend at most **0.629 CPU s** after the initial
curved gate, or would need to cut another measured scope. With the current
rejection point, the named fallback would have to save about **17.7%** of
its measured CPU time to close the entire gap on its own. No tested early
observable supplies that refusal and preserves the accepted controls.

The original and post-handoff workers retain the same scientific
publication. On 0255 the fixed-zero/fitted errors are **627.115/564.894 m**
and conditional RF RMS **111.857/111.754 Hz**, with **3,704 ordered owner
and role rows per arm**, the full 179-point grid, path, and eight identical
routed PNGs across the two routed workers. These are earlier observed
outputs. The replay supplies no new timing or artifact match.

The reduction checks the frozen input digests and the installed paired gate
source. It uses the staged 0169 trace digest listed in the earlier
publication binding. Component tests cover exact gate order, track
failures, phase and region bounds, and unsealed input refusal.
[Replay source](early_lean_refusal.py) ·
[Tests](../../../tests/pipeline_eval/test_early_lean_refusal.py) ·
[Machine receipt](measurements/early-lean-refusal-0255.json.gz),
uncompressed SHA-256
`b30d0a5af6652f1532da42e8bcfa2c1a32dcf0b037595545700930c599b63d56`.
