# Independent-noise replication of both fixed125 refinements

Proposed next freeze, not yet executed. Preserve both125 estimators exactly,
including original-native-bin parity,±.5bin bounds, power-decrease rejection,
three Newton steps, original admission and every failure. No best-variant
selection by condition or additional estimator adjustment.

Repeat the identical5phase×2amplitude×3cutoff design with **16 new seeds
127000..127015**, reused across conditions:480 new conditioned inputs. Keep
phases[-.4,-.2,0,.2,.4]Delta, amplitudes[.25,1], cutoffs[.00015,.001,.020]s,
noise RMS1, epoch/acquired CFO/offset0 and original margin.025 only. Freeze
all generating/refinement sources and protocol before native calls. Native
coarse score/bin parity remains required; do not compare against122's random
realizations as if they were the same inputs.

Report the same all-cell, admitted/unconditional metrics, paired regressions,
16-seed dispersion and runtimes as125. This checks new-noise replication
within the same fixed synthetic family, **not** blind acquisition, new physical
signal validation or positioning generalization. No new phase/orientation,
fading model, tuning or method selection. Actual driver/freezer preparation
and parent publication must precede execution.

The driver imports immutable125 refinement and122 generation sources. One
native call per input independently supplies the baseline; native/Python winner
and score parity are required. One original margin verdict applies to both
variants. Completed rows are flushed to append-only JSONL; failures preserve
completed rows, failed case and traceback in a terminal receipt. A failed
case's exact native-call count may be unknown and is explicitly reported.
Exclusive claims prevent automatic restarts. No trial has been run.
