# Direct lane-offset sharing fails at the inherited hypotheses

Do not replace per-track offsets with an offset transferred directly from other
candidate tracks. On3,925 supported same-receiver/exact-RF cases, median held
error rises from**102.61Hz to3,195.91Hz**. Only34 cases improve. The result holds
across all nine panels, not merely one receiver or dataset.

| Dataset | Supported / eligible cases | Own training-offset median error Hz | Shared-offset median error Hz | Improved cases |
|---|---:|---:|---:|---:|
| DS7 | 1336/1346 | 97.35 | 2441.69 | 9 |
| DS8 | 1279/1311 | 101.26 | 3191.93 | 14 |
| DS9 | 1310/1326 | 113.15 | 4298.03 | 11 |
| All | 3925/3983 | 102.61 | 3195.91 | 34 |

These are medians of per-case held median absolute **circular native-frequency
errors**, after accounting for integer alias equivalence. They are not position
errors or independent Doppler-truth measurements. Each comparison uses the same
supported target cases and held observations for its two arms.

![Conditional offset-sharing comparison](comparison.png)

## Why test this

The contrast localization model removes one constant frequency offset per track.
That is robust to transmitter/receiver offsets, but it discards absolute-frequency
relationships between tracks. A common offset within one recording, receiver and
RF would provide an additional constraint if it were supported by the data.
Earlier slope-transfer and single-excerpt waveform tests do not establish that
these constant offsets can be shared.

## Frozen method

Use the3,983 previously exported conditional cases from all nine eight-scan panels.
Their existing selection requires candidate weight times signal responsibility
at least0.5, and five training observations spanning five seconds. No new quality
selection was introduced. Case outputs were checked against the original evidence
hashes. This subset is smaller than the full4,328-track geographic objective.

Convert residuals from11.2GHz canonical units into native Hz using actual RF.
Track offsets can differ by integer pilot-frequency aliases, so comparisons wrap
with period`1/4.4 microseconds = 227272.727...Hz`. Each donor's offset is its
arithmetic training-residual mean, then wrapped. Aggregate donor offsets with a
deterministic circular L1 median, first per catalogue number and then across
numbers, giving each number equal weight. Require three distinct donor numbers.

All donors share the target recording, receiver and exact RF. Exclude the target
track and every donor with its candidate number. No held residual sets an offset,
selects a donor or tunes a threshold. The comparison arm uses the target's own
training-mean offset. Both predict its unchanged held observations. Fifty-eight
same-RX cases lack sufficient donor numbers; all unsupported cases remain in
the evidence and coverage counts.

The opposite-RX/exact-RF comparison supports3,924 cases, with median own/shared
errors102.61/4,725.55Hz and38 improvements. Its cohort differs slightly from the
same-RX cohort. It is a comparison, not a guaranteed physical negative control:
receiver paths may share hardware or common signal effects.

## What is learned, and what remains open

At the inherited candidate, location and timing hypotheses, forcing one common
offset is far too restrictive. Median training-only donor dispersion is2,394.63Hz;
median target-versus-donor offset disagreement is3,164.15Hz. This is much larger
than the approximately100Hz own-track held residual scale.

However, the shared offsets remain clustered on a few-kilohertz scale after
alias handling. The result therefore motivates a **soft shared-offset hypothesis**,
not automatic rejection of all offset coupling: allow track-specific deviations
while fitting a common receiver/RF offset jointly with position and associations.
That model would use the additional absolute-frequency relationship without
forcing all residual offsets to agree exactly. It needs its own frozen likelihood,
width policy and geographic/held evaluation; no benefit is established here.

The current test freezes candidate identities and geometry derived from training,
including the target's training data. They are not independently verified satellite
identities. Wrong associations, location/timing error, transmitter differences,
receiver drift or combinations can cause offset dispersion. Donors are drawn
across the recording, without a contemporaneity requirement. This experiment
does not distinguish those causes or test whether joint recalibration would
recover a better solution. Cases sharing recordings/candidates are correlated.

The cached geographic baseline remains unchanged, and consistent sub-kilometer
accuracy remains unresolved.

## Evidence and execution

- [PROTOCOL.md](PROTOCOL.md): frozen donor construction and evaluation rules.
- [results.json](results.json): every supported/unsupported case, donor numbers,
  offsets, dispersions, own/shared errors, summaries and input/code hashes.
- [TABLE.md](TABLE.md): complete per-panel aggregation.
- `model.py`, `run.py`, `summarize.py`, `test_model.py`: implementation and tests.

Three tests pass: integer-alias invariance, circular median across the wrap
boundary, and excluding the target candidate with balanced donor-number support.
Ruff checks and source hashes pass. Execution finished within one120-second
single-thread numerical cap using existing residual exports. No IQ was read,
RF collected, production model changed or geographic fit run. Artifacts are
local and have not been newly published to remote main.
