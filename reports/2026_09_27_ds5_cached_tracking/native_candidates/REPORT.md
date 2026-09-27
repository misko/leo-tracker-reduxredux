# Broader native search: two candidates per probe

This experiment spends some of the native detector's measured speed advantage
on a second acquisition hypothesis per probe. It preserves the engine's tone
conditioning, support selection, fractional timing, full-aperture exact/control
score, and the existing causal tracking controller. The only engine profile
change is `LEO_PRESENCE_CANDIDATES=2`, using the existing safe two-slot capacity.
Four-candidate support would require a separate implementation change.

The fixed evaluation is in `EVAL_DESIGN.md`; `source_lock.json` pins 74 files
before outcomes, including both builds, the original detector, component tests,
assessment helpers, manifests and current application backend. All comparisons
use both receivers inside the timed call, one P-core and numerical thread counts
one. Conversion, native processing, state and observation capture are timed;
initialization, loading, hashing and post-call serialization are excluded.

Unlike the prior decision-only receipts, this experiment preserves all returned
blind and guided observations, including rejected candidates. This permits
post-outcome diagnosis without rerunning IQ or changing the frozen variant.

## Original constructed controls

All 42 physical cases / 84 receiver cases completed with stable sources and
immutable inputs. Original one-candidate blind, two-candidate blind, and
two-candidate tracked methods each produced 52 injected-truth-associated
positives and 32 constructed true negatives, with zero required-policy failures.
All three methods agreed in activity and associated identity on all 84 receiver
cases. The tracked route had four guided accepts, four guided failures with
blind fallback and 76 cold calls. These repeated-array sequences test mechanics;
they do not establish field cache-hit frequency.

Each blind method processes 924 probe occurrences in these controls. The
one-candidate method returned 924 candidate-zero observations; the broader
method returned those plus 924 candidate-one observations. Two-candidate
complete physical calls were approximately 19–51 ms here; all calls finished
below 120 ms. There is no application comparison in this control stage, so this
stage makes no full-scanner speedup claim.

## New constructed development dataset

All 26 physical / 52 receiver cases completed. Each native method produced 38
truth-associated positives, ten constructed true negatives and four inactive
weak pilots, with no unassociated positive decisions. The second candidate did
not improve detection on this fixed power ladder. Known-negative outcomes and
application-relative counts were unchanged.

| Rate | Application median CPU | K1 blind median CPU | K2 blind median CPU | K2 tracked median CPU | K2 blind aggregate speedup | K2 tracked aggregate speedup |
|---|---:|---:|---:|---:|---:|---:|
| 2.5 MS/s | 1441.92 ms | 15.81 ms | 21.95 ms | 22.20 ms | 65.33x | 70.22x |
| 5 MS/s | 3660.98 ms | 31.29 ms | 41.61 ms | 40.32 ms | 89.15x | 94.25x |

Ratios use sums of paired CPU rather than ratios of medians. Every native call
was below 120 ms in CPU and observed wall time. One call per case is development
evidence, not a population latency distribution or a field false-alarm estimate.

The second candidate changes the selected injected trajectory in three receiver
cases: RX1 of the last causal-sequence visit at each rate and RX0 of the 5 MS/s
multiple-hypothesis case. K1 chooses `pilot-b`, while K2 blind chooses `pilot-a`.
Both are valid injected trajectories. On the 5 MS/s last sequence visit,
tracking retains `pilot-b` rather than switching to K2 blind's `pilot-a`.
These are real selection differences, with no change in physical truth or
application-relative retention counts. The output still represents one pair,
not a complete inventory of simultaneous signals.

Independent captured-observation auditing found candidate zero exactly equal
to the original engine in all 924 control and 572 diagnostic probe occurrences,
excluding timing instrumentation. K2 contributes 924/572 extra observations,
of which 25/69 pass the individual positive gate. None of the extra control
observations changes a selected pair; three diagnostic pairs use candidate one
for both observations. Thus the expansion changes available hypotheses and
selection, not the existing first hypothesis's scoring.

The two diagnostic reference-identity disagreements remain the same late-only
symbol-region cases. Native matches injected truth, while the application uses
an early-symbol statistic; they are not new physical sensitivity losses.

## Recorded chronological replay

All 64 physical visits / 128 receiver occurrences completed within the
300-second bound (176.5 seconds), with all 74 locked sources unchanged.

| Rate | Application median CPU | K1 blind median CPU | K2 blind median CPU | K2 tracked median CPU | K2 blind aggregate speedup | K2 tracked aggregate speedup |
|---|---:|---:|---:|---:|---:|---:|
| 2.5 MS/s | 1435.63 ms | 15.29 ms | 21.34 ms | 19.91 ms | 67.11x | 86.18x |
| 5 MS/s | 3846.34 ms | 31.05 ms | 41.79 ms | 22.72 ms | 91.88x | 130.32x |

All native physical calls finished below 120 ms in CPU and observed wall time.
K2 blind maximum observed wall time was 23.47/47.41 ms and tracked was
23.22/45.80 ms at 2.5/5 MS/s. These are complete compute calls on the fixed
development prefix; IO and initialization remain excluded.

| Application-relative metric | K1 blind | K2 blind | K2 tracked |
|---|---:|---:|---:|
| Associated positive receivers, 2.5 MS/s | 33/37 | 33/37 | 33/37 |
| Associated positive receivers, 5 MS/s | 34/42 | 34/42 | 33/42 |
| Associated positive receivers, total | 67/79 | 67/79 | 66/79 |
| Associated positive visits, total | 56/56 | 56/56 | 55/56 |
| Active receivers without an associated application pair | 5 | 6 | 7 |

K2 blind recovers none of the original twelve missing receiver identities.
It adds one receiver activation / visit at 2.5 MS/s where K1 and the application
are inactive. All real-data additions remain unadjudicated; the increase is
not a proven new physical false alarm or a proven recovered signal.

The tracked difference is 5 MS/s visit 1091, RX1. K1 and K2 blind choose probe
0/2 evidence at about 1219.5 local samples and 20.6 kHz. K2 tracking confirms
its prior probe 0/2 hypotheses at about 1644.1 samples and 63.3 kHz, with fresh
margins 0.1083/0.2009. It remains active but fails association to the application
and current blind pair. Thus all 56 application-positive visits still receive
an active decision, but only 55 retain an associated identity. The data do not
establish whether the alternate track is another physical signal or erroneous
evidence. A successful point confirmation is insufficient to guarantee that
the currently selected blind-search identity is preserved.

Tracked routes were 65 cold, 33 guided accepts and 30 guided-failure fallbacks.
Five of 73 K2 blind active receiver pairs use candidate one, yet none recovers
an original reference loss. The second candidate increases compute and changes
some selections; it is **not adopted as a receiver-coverage improvement**.
The original one-candidate version remains the faster development baseline.

The independent `OBSERVATION_AUDIT.md` found exact candidate-zero science
agreement in all 2,904 probe occurrences across stages. More importantly, none
of the twelve remaining real losses has a reference-matching pair anywhere in
the complete captured positive K2 inventory. Eleven have no compatible positive
native pair; the twelfth has eight compatible pairs at the wrong frequency
identity. Changing only downstream pair selection cannot recover these rows.

A further receipt inspection found that the 2.5 MS/s visit-1101 RX1 application
inventory lies at approximately 510.5–511.0 kHz physical CFO, about one 227 kHz
alias from the native identity. However, its strongest pair is actually scored
at approximately 398 kHz, with an added residual near 112 kHz. All twelve lost
receivers' strongest application pairs have acquired/scoring CFO within the
native +/-400 kHz range. Physical CFO alone therefore does not demonstrate an
acquisition-range exclusion. V3 guided scoring also replaces the old absolute
physical-frequency rejection with an innovation check against expected physical
CFO. The new fixed-point diagnostic must preserve this distinction rather than
classify every physical CFO above 400 kHz as unsupported.

The next targeted diagnostic should score fixed reference timing/frequency
hypotheses for these losses through the native statistic, then distinguish a
missing proposal or CFO range from a different final statistic. It should keep
the full frozen development results and not reinterpret this unsuccessful
candidate-count intervention as an accuracy improvement.

## Qualification scope

This remains an isolated development experiment. No production component,
published contract, reference checkout or golden fixture is modified. No RF is
collected. Reserved validation IQ remains ungenerated and the original holdout
remains unopened. A result must retain the stated detection/measurement coverage
as well as reach 10x compute reduction before it supports the intended goal.

The full research suite passes 463 tests and 11 subtests. This validates the
implementation checks, not the rejected scientific coverage hypothesis.
See the immutable `results.controls.json`, `results.diagnostic.json`, and
`results.real.json` receipts, plus `POSTHOC_CHANNEL_REUSE.md` for a separate
read-only check of direct cross-receiver reuse on the preceding replay.
