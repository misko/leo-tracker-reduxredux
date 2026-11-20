# Can fast pilot factors recover capture-era GLRT winners?

The distilled gate met both the 5% and 10% position targets on one of the
four narrow holdouts in each calibration. It published all four, with errors
from 0.49 to 3.29 km. The same-count margin control recovered slightly more
teacher families and used less summed position CPU across the three complete
matched comparisons. On the two supplementary wide recordings, strongest
margin met both position targets twice and the distilled gate did so once.

The frozen gate recovered fewer capture-era winner families than the
strongest-margin control at the same number of compact receiver inputs.
Across four narrow-detector holdouts, the learned gate recovered 13,237 of
15,407 shareable winners (85.9%). Strongest margin recovered 13,276 (86.2%).
Stock recovered 14,840 (96.3%) with 17,785 admitted probes, versus 14,917 for
each reduced method. The learned gate admitted 801 probes with no teacher
winner, versus 738 for strongest margin and 1,766 for stock.

The two supplementary wide-detector recordings had the same ordering.
Learned recovered 7,769 of 8,353 shareable winners (93.0%), strongest margin
recovered 7,834 (93.8%), and stock recovered 8,213 (98.3%). The frozen model
saw narrow factors from two other recordings during training. All eight
recordings came from the same roof. The supplementary result measures
transfer across recordings and detector range. [Teacher agreement](teacher-agreement.csv)

## Position and calibration

Each cell gives the `c = 0` and fitted-`c` horizontal errors in kilometres.
Both thresholds compare each recording to its original no-repair v5 result.
The other three archived v5 controls appear in the position figures and CSV.

| Recording | Original v5 | Stock | Distilled | Same-count margin | Teacher-family oracle |
|---|---:|---:|---:|---:|---:|
| DS26-0237 | 0.362 / 0.271 | 0.889 / 0.814 | 0.572 / 0.511 | 0.453 / 0.408 | 0.815 / 0.707 |
| DS29-0174 | 0.885 / 0.917 | 1.161 / 1.224 | 1.051 / 1.080 | 1.358 / 1.371 | 1.319 / 1.341 |
| DS26-0122 | 0.751 / 0.747 | 1.330 / 1.330 | 3.277 / 3.294 | 3.804 / 3.804 | 0.589 / 0.594 |
| DS29-0247 | 1.320 / 1.458 | Timeout | 0.497 / 0.494 | Timeout | Timeout |
| DS26-0144, wide | 0.192 / 0.229 | 0.162 / 0.180 | 0.082 / 0.095 | 0.113 / 0.143 | 0.158 / 0.148 |
| DS29-0491, wide | 1.767 / 1.780 | Timeout | Timeout | 1.350 / 1.323 | 1.589 / 1.570 |

At both thresholds the narrow holdouts count one pass for distilled
(DS29-0247), one for the oracle (DS26-0122), and zero for stock and
same-count margin. The wide supplements count one pass each for distilled
and stock and two each for the oracle and same-count margin.
All timeouts remain in the denominators.

Fitting `c` changed the distilled narrow conditional RF RMS by −0.094 to
+0.122 Hz. Three recordings had lower RMS. Position errors improved on two
recordings and increased on two. The conditional frequency score decreased
on two and increased on two. DS26-0122 illustrates the divergence. Its
conditional RMS fell by 0.014 Hz while error increased by 0.018 km and the
conditional frequency score increased by 14.20.
[Per-recording position and frequency](scores.csv) ·
[Four v5 controls](v5-controls.csv) · [Paired calibration changes](calibration.csv) ·
[Position figures](charts/README.md)

## The frozen gate

The constrained logistic fit used 71,747 fast candidate families from
DS26-0036 and DS29-0082. The standardized slopes were 1.339 for margin,
0.937 for margin gap to the strongest rival, 0.693 for negative log native
rank, and zero for negative control score. The intercept was −4.379 and the
logit threshold was −0.483. The resulting training prevalence was 18.90%.
Each feature contributes monotonically with the representative fixed. A change
in the margin-selected representative can also change native rank and control
score.

Held labels used exact shared physical probe support. Within a probe the
matcher folded both the 750 Hz frame epoch and CFO ambiguity, then grouped
complete-link duplicates before requiring mutually unique family matches.
The four narrow recordings had 17,492 teacher-positive probes. Of those,
15,407 had a shareable fast family, 367 were ambiguous, 1,715 had no fast
family match, and three had a group match without a direct teacher-winner
member match. The model and count control each retain a single unmodified
fast measurement per admitted probe. [Protocol](PROTOCOL.md) ·
[Frozen model](frozen-model.json) · [Replay plan](replay-plan.json)

## Interpreting the oracle and runtime

The teacher-family oracle uses a held teacher label to select an existing
fast candidate, including its own CFO branch. Compact noise estimation
requires a strictly positive native margin. Three raw teacher matches failed
that precondition. The revised oracle drops those three representatives and
publishes the three revised attempts alongside the original outcomes.
[Oracle amendment](ORACLE-AMENDMENT.md) · [Original prediction lock](prediction-lock.json) ·
[Amended oracle lock](oracle-amendment-lock.json)

The measured boundary begins with complete stored fast factors and ends at
compact position. All methods use the original truth-free offers, causal
TLEs, clocks, and track settings. The compact solver fits both calibration
arms against the same selected inputs. Matched historical narrow-detector
raw wall times appear separately in the resource table. The original v5
wall times use their historical measurement boundary. The replay measures
runtime after GLRT. Saved-IQ timing comes from the historical arm.
[Work and stage times](resources.csv) · [Stage figure](pilot-distillation-stages.png)

Three narrow recordings completed all three deployable arms. Their summed
position CPU was 212.0 s for stock, 170.9 s for learned, and 154.6 s for the
same-count strength control. Compact projections totaled 18,278, 14,843,
and 14,595, respectively. The learned input gate, including read and
serialization, used 0.71 to 0.82 CPU seconds on those three runs. DS29-0247 stock and
strength exceeded the 150 s wall cap. On wide DS29-0491, stock and learned
exceeded the cap. Each pair was measured once, with shared host load
and the same core per recording. These timings describe the completed pairs.

The earlier univariate study calibrated wide fractional margin to teacher
prevalence using the same two development recordings. Its held cohort shared
DS26-0237 and DS29-0174 with this trial. The historical cutoff lost 1.61
percentage points of teacher-positive probe recall and saved 6.5% summed
position CPU. Its largest geographic errors increased in both calibrations.
That test counted positive probes. This trial also checks whether the
winning peak belongs to the teacher's physical family.
[Historical wide-margin admission](../../receiver-core/margin-admission/README.md)

## Reproduce the study in scratch

The source archive preserves the six pilot Python files used for the original
training, position replay, oracle amendment, and scoring. Each file matches
the digest in its original receipt. The live source adds scratch output paths
and passes Ruff. A fresh fit reproduced the measured coefficients, threshold,
and training diagnostics exactly. The current scorer regenerated the same
score tables and stage PNG from a scratch copy of the sealed predictions.
[Measured sources](measured-sources.tar.gz) · [Source hashes](measured-source-lock.json)

```bash
pilot_run=$(mktemp -d /var/tmp/leo-pilot-fresh.XXXXXX)
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1

taskset -c 18 .venv/bin/python -m tools.pipeline_eval.qualification.pilot_distill_trial \
  freeze --report "$pilot_run/report"
taskset -c 18-21 .venv/bin/python -m tools.pipeline_eval.qualification.pilot_distill_trial \
  replay --report "$pilot_run/report" --work "$pilot_run/replay"
taskset -c 18,20,21 .venv/bin/python -m tools.pipeline_eval.qualification.pilot_distill_oracle \
  "$pilot_run/replay" "$pilot_run/oracle" --report "$pilot_run/report"
taskset -c 20 .venv/bin/python -m tools.pipeline_eval.qualification.pilot_distill_results \
  --report "$pilot_run/report"
.venv/bin/pytest -q tests/pipeline_eval/test_pilot_distill.py
```

To regenerate the position charts directly from the published measurements,
pass the study directory as evidence and render to a fresh directory.

```bash
.venv/bin/python - <<'PY'
from pathlib import Path
from tempfile import mkdtemp

from tools.pipeline_eval.qualification import screening_figures
from tools.pipeline_eval.qualification.pilot_distill_trial import REPORT

charts = Path(mkdtemp(prefix="leo-pilot-charts-", dir="/var/tmp"))
screening_figures.generate(charts, evidence=REPORT)
print(charts)
PY
```
