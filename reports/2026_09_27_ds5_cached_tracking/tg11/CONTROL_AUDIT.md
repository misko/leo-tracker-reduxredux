# Independent TG11 stage-0 control audit

This is a read-only audit of the frozen stage-0 receipt. No detector or DSP call
was rerun. The receipt is complete and internally consistent with the frozen
source lock and dataset contract.

## Integrity and inventory

- `control_results.json` SHA-256:
  `285023e3b1a489c68d18cdb72de9d89f0a36f6c58b74126f773a7b6ac4eb9ce6`
- `source_lock_stage0.json` SHA-256:
  `73e3c8b356e8b5f6c5359cc688d7e28fbf722ace541a909106e3d029b1fb92d4`
- Every file in the source lock still matches its recorded digest.
- The locked and independently recomputed membership digests both equal
  `41c3e268e52a7c8295c64ec0e137e28d153d99bf1a232e9517c5958dc7ededb7`.
- The 42 physical receipt rows exactly match the frozen order, identifiers,
  sequence membership, visit indexes, source counters and IQ hashes: 32 base
  controls followed by 10 sequence occurrences.
- All 84 receiver results are present: 64 base-control receivers and 20 sequence
  receivers. All rows report immutable input, eleven screened windows and a
  complete fresh result. The receipt status, source stability and every gate are
  passing; no holdout was opened.

## Scientific outcomes

All base-control receiver rows matched their declared constructed truth:

| Constructed content | Receiver rows | Active | Inactive |
|---|---:|---:|---:|
| Single pilot | 32 | 32 | 0 |
| Two pilots | 4 | 4 | 0 |
| Pilot plus strong tone | 4 | 4 | 0 |
| Noise only | 12 | 0 | 12 |
| Tone only | 12 | 0 | 12 |

Across associated active rows, the largest recorded timing error was 0.441
sample and the largest tracking-CFO error was 52.91 Hz. These are comfortably
inside the frozen 2 us and 8 kHz gates. The minimum accepted member margin was
0.849, so this control set does not exercise near-threshold behavior.

The eight original finite-pilot receiver rows used only the source-supported
nonoverlapping probes. Lower-edge cases selected probes 1 and 3; upper-edge
cases selected probes 7 and 9, at both sample rates and on both receivers. No
finite-pilot result associated by circular phase to an aperture outside the
injected 20 ms segment. Their maximum timing and CFO errors were 0.162 sample
and 45.74 Hz respectively.

Every causal-sequence receiver also passed:

- Quiet-to-pilot: two quiet visits remained inactive, then the first
  pilot-bearing visit took `blind_cold` and associated to the pilot.
- Pilot dropout: both establishment visits were active; the following noise and
  tone visits were inactive, so no stale positive was emitted.
- Changed pilot: the final timing/CFO change took
  `blind_screen_disagreement` and associated to the new injected pilot.

Integer source-coordinate reconstruction is exact for every active pair:
`source_epoch_counter` equals the integer visit counter plus probe start and the
whole local epoch, while `source_epoch_fraction` retains the fractional part.
All pairs use one receiver, nonoverlapping probe starts and at most 8 kHz mutual
tracking-CFO difference.

## Route inventory and limits

| Route | Receiver results | Active | Inactive |
|---|---:|---:|---:|
| `blind_cold` | 74 | 46 | 28 |
| `blind_screen_disagreement` | 10 | 6 | 4 |
| Guided | 0 | 0 | 0 |

Every result performed eleven blind observations and recorded zero guided
attempts; all 52 active decisions came from a blind route. Stage 0 therefore validates the blind resolver, injected-truth
association, fail-open sequence behavior and lack of stale decisions. It does
not provide saved-IQ evidence that the guided route accepts a track, improves
cost, or preserves a real comparator decision. Guided behavior is covered only
by component tests at this point.

The controls are strong constructed examples and their accepted margins are far
from the decision boundary. Noise/tone outcomes are constructed false-alarm
evidence, not a field false-alarm estimate. Reused sequence arrays declare
virtual counter and phase resets and test causal state semantics; they are not
new independent RF observations. The per-row times are explicitly diagnostic
and are not a paired application speed comparison.
