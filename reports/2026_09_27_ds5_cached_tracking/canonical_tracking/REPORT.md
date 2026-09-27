# Canonical tracking constructed-control result

The native-proposal plus current Python canonical-confirmation detector exercised
its actual cache path, but it failed the frozen constructed-control specificity
gate. The complete 84-receiver cached inventory and the 20-receiver all-blind
sequence comparator were preserved. No real replay followed.

## Cache and fallback behavior

Both receivers guided successfully on the repeated identical pilot in each of
the `pilot-dropout` and `changed-pilot` sequences: four guided receiver results
in total. Each guided result used four canonical point scores and skipped native
screening and blind acquisition. The changed-pilot final visit failed open via
`discovery_guided_failure` on both receivers and associated with the new injected
trajectory. The noise dropout remained inactive on both receivers. There were
no stale cached positives.

The cached route inventory was:

| Route | Receiver rows |
|---|---:|
| `discovery_cold` | 76 |
| `guided` | 4 |
| `discovery_guided_failure` | 4 |

This provides saved-IQ evidence that the cache path can accept a stable repeated
pilot and that an incompatible track fails open. It does not establish real-signal
retention or a production cache-hit rate.

## Scientific failure

Six of the twelve base tone-only receiver controls became active:

- RX1 of the original 2.5 Msps lower tone;
- RX0 of the original 2.5 Msps upper tone;
- both receivers of the original 5 Msps lower tone;
- RX0 of the original 5 Msps upper tone;
- RX1 of the adversarial 5 Msps tone.

The same original lower-tone RX1 also became active in the final dropout sequence
step for both cached and all-blind executions. Thus seven of 84 cached truth rows
failed. Their selected member margins ranged from 0.03633 to 0.06722, above the
unchanged inclusive 0.025 gate. Pilot, two-pilot, pilot-plus-strong-tone and noise
base controls passed their injected-truth gates.

The all-blind comparison used the same canonical detector with fresh state for
each visit and reproduced the tone activation. The failure comes from the new
discovery-plus-canonical-confirmation detector, rather than stale cached state.
The previous native TG11 control run applied its native nuisance-conditioned
science and kept these tones inactive; replacing final acceptance with raw
canonical point scores removed that protection. This result must not be repaired
by relabeling constructed tones or tuning the margin threshold after exposure.

A read-only post-outcome timing diagnostic found that every selected tone pair
was grossly inconsistent with one 750 Hz frame lattice. Their circular phase
errors were 127--419 us, while a diagnostic allowance of 2 us plus 50 ppm over
the selected probe separation was only 3.5--4.5 us. The errors exceeded that
allowance by 28x--120x. By comparison, all 40 truth-associated active base-pilot
pairs had at most 0.4 us phase error and at most 0.134x of the same allowance.
This was not a frozen gate and does not rescue this result. It identifies a
concrete future hypothesis: CFO consistency alone can pair unrelated tone-driven
epochs, while requiring a coherent frame lattice may reject them. Any such rule
needs a new preregistered detector and independent controls.

## Sequence timing diagnostic

The complete ten-step sequence inventory, both receivers, measured:

| Mode | Median process CPU | Median wall |
|---|---:|---:|
| Cached | 571.603 ms | 571.634 ms |
| All blind | 700.246 ms | 700.262 ms |

This is a 1.225x CPU reduction on this deliberately small sequence inventory.
It is a within-detector diagnostic, not a 10x claim and not a comparison to the
full scanner. One warmup and three counterbalanced repetitions were run with
state restored before each repetition; the cached scientific sequence was then
committed exactly once.

The runner completed in 9.35 seconds with stable source and input hashes. No new
development set, real replay, holdout, RF, production or ARM work was opened.

Artifacts:

- `source_lock.json`: pre-outcome detector, runner, native, scorer and dataset
  provenance.
- `control_results.json`: all decisions, associations, routes, scores, timing
  repetitions and gate outcomes.
- `CONTROL_PROTOCOL.md`: frozen inventory, route requirements and stopping rule.
