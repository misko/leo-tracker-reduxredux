# Conservative RX updates: positive replay gains fail the geometry-specific control

This development replay uses all 344 existing calibration tracks in both
directions. The outcomes were previously inspected. It is not independent
validation and does not measure geographic resolution. No model was promoted.

The primary update was fixed to 50% frequency-only posterior plus 50%
RX-updated posterior. Sensitivities 25%/75%, endpoints, reversed RX orientation,
and candidate-independent null were specified in the runner before execution.
After seeing the reversed control outperform normal RX forward, two additional
posthoc controls blended the frequency posterior with either a uniform candidate
distribution or the frozen training prior. Neither uses receiver geometry.

| Fixed 50% blend target | Forward gain | Reverse gain | Recordings improving, forward/reverse |
|---|---:|---:|---:|
| Normal RX update | +0.002103 | +0.008979 | 3/6; 6/6 |
| Reversed RX update | +0.004551 | −0.000353 | 4/6; 2/6 |
| Uniform over the same shortlist | **+0.088390** | **+0.097273** | **6/6; 6/6** |
| Frozen training prior | +0.039935 | +0.047624 | 6/6; 6/6 |

Values are occupied-second-weighted decreases in held-frequency NLL per
observation. Candidate identity is still shared across the held block; the
uniform control is not independently redrawing identity at every observation.
It introduces no candidates, changes no CFO, and uses no held evidence to form
the blend. It retains probability for the existing top-three training shortlist.

## What this changes

The conservative update bounds the damage from any individual RX update and
produces positive average development gains. **Those gains are not evidence of
useful receiver geometry:** generic diversification is much more effective on
these saved scores. The frequency-only conditioning distribution appears too
concentrated for predicting the other block under the current model. Possible
causes include correlated likelihood contributions, within-track mismatch,
unmodeled drift/timing, or genuinely incorrect candidate assumptions. This
experiment does not distinguish those causes or establish physical identity.

Normal RX sensitivity gains at weights 0.25 / 0.5 / 0.75 are:

- Forward: +0.002191 / +0.002103 / +0.001188.
- Reverse: +0.007516 / +0.008979 / +0.009400.

The unblended RX update remains −0.004239 / +0.000359. No best weight was
selected. Null gains are at floating-point zero (maximum pooled magnitude
below 4e-18). Endpoint scores reproduce the saved baseline/RX scores and every
blended track satisfies the analytic worst-loss bound.

## Next decision

Do not run a geographic search merely because the 50% RX blend is positive.
First test RX **incrementally over a calibrated, geometry-free association
baseline**. The baseline and all frequency preprocessing need training-only
calibration; grouped randomized partitions must retain correlated observations
together. Include normal, reversed, and geometry-free controls, and retain
independent Sacramento/Reno candidate construction. A reliable incremental
predictive benefit should precede an independently evaluated location search.

This changes the priority from tuning receiver weights to understanding and
calibrating frequency association confidence. It does not establish that RX
geometry is useless; it prevents attributing a generic uncertainty repair to
physical direction information.

## Artifacts

- `conservative.py` and `conservative-results.json`: all five blend fractions,
  both directions, normal/reversed/null controls, per-track scores and bounds.
- `geometry_free_controls.py` and `geometry-free-results.json`: the two
  additional 50% controls with complete per-track and recording outcomes.
- Source/core hashes are retained in the result files; all outputs refuse
  overwrite. Scripts read only existing JSON and do not access RF or services.
- Tests cover mixture identities, endpoints, loss bounds, null behavior,
  malformed input rejection, and receipt reconstruction.
