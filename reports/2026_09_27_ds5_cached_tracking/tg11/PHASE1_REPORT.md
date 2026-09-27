# TG11 phase-one paired cost result

The bounded four-visit phase completed with stable sources and deterministic
outputs. TG11 passed both performance gates but failed the frozen scientific
gate, so phase two was not authorized or run.

| Rate | Current scanner median CPU | TG11 median CPU | CPU speedup | Absolute budget | Cost gate |
|---|---:|---:|---:|---:|---|
| 2.5 Msps | 1515.495 ms | 16.032 ms | 94.53x | 143.427 ms | pass |
| 5 Msps | 4071.329 ms | 33.150 ms | 122.81x | 389.020 ms | pass |

These timings cover complete CI16-to-decision calls for both receivers, with one
warmup and three counterbalanced repetitions on P-core 0 and all declared
numerical thread counts fixed to one. Each repetition restored the pre-visit
causal snapshot, and each physical visit advanced state exactly once. Inputs and
source hashes remained unchanged.

Three of four visits passed the comparator association gate. The second 2.5 Msps
visit was inactive in the full ten-candidate scanner: no candidate passed the
margin gate, and its largest margin was 0.016678. TG11 emitted an RX0 pair from
probes 4 and 10 with margins 0.095757 and 0.114112 near -86.1 kHz. Because the
comparator inventory was empty, this is an unadjudicated additional decision and
fails the conservative development gate. It is not labeled a physical false
positive because the recorded visit has no truth label.

A read-only comparison against all 110 sub-threshold RX0 application candidates
also found no near identity. The nearest application candidate to the probe-4
TG11 observation differed by 121.64 samples (48.66 us) and 84.72 kHz; the
nearest to the probe-10 observation differed by 123.82 samples (49.53 us) and
84.73 kHz. Both exceed the frozen 2 us/8 kHz identity tolerances. This diagnostic
does not retune either detector or adjudicate which physical interpretation is
correct.

All eight receiver decisions in this phase used `blind_cold`. There were no
guided attempts or cache accepts: the four selected cases use different channel
keys within each rate. The large measured speedup therefore demonstrates the
cost of TG11's smaller blind decision detector, not acceleration from an already
tracked signal. Stage zero likewise recorded zero guided attempts. Cache-path
benefit remains supported only by component/state-machine tests in this staged
experiment.

The native decision-band profile is scientifically different from the current
Python ten-candidate comparator, despite retaining the three comparator-active
visits here and passing the constructed-control stage. The result cannot support
promotion, broader real replay, a field false-alarm claim, or a claim that the
general-compute objective is complete. No holdout, RF, or ARM work was performed.

Artifacts:

- `source_lock_phase1.json`: frozen phase-one sources and membership.
- `phase1_cost_results.json`: full comparator responses, both receiver decisions,
  repetitions, timing summaries, associations, and gate outcomes.
- `run_phase1_cost.py`: frozen paired runner.
