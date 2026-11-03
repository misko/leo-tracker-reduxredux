# Remaining ARM discrepancies after the authorized reference-10 exception

Reference 10 is excluded by the user's explicit request, with the exception
bound to the exact reference/output hashes in `exceptions.json`. The original
63-reference evaluation remains unchanged. The reviewed comparison has 62
eligible reference segments, 46 represented and 16 discrepancies. This is
server-segmentation agreement, not independently established physical recovery.

## All remaining segments, longest first

Counts below are matching canonical sources, not raw candidate counts. Input
means a matching ARM detection exists; output means the best individual physical
ARM output contains it. A complete match additionally requires 80% in-span
source purity. Zero output means no matching source in any output, not merely
an unsuccessful one-to-one assignment.

| Ref | Duration | ARM input / server | Best output / server | Diagnosis |
|---|---:|---:|---:|---|
| 2 | 50.11 s | 68/84 | 67/84 | Near-complete, 79.8%; one source below cutoff. Fourteen absent windows are fully coarse-gated, two fail margin. The unassigned available source precedes a 7.12 s matching-evidence gap. |
| 30 | 34.38 s | 28/40 | 28/40 | Tracker recovers all available matching sources. Eleven absent windows fully coarse-gated; one fails margin. |
| 8 | 32.23 s | 10/42 | 5/42 | All 32 absent windows fully coarse-gated. Matching evidence splits across 18.68 s and 5.73 s gaps; late fragment retained. |
| 34 | 32.13 s | 35/45 | 32/45 | Nine windows coarse-gated, one incompatible CFO; 6.58 s matching-evidence gap exceeds tracker 4 s gap policy. |
| 47 | 30.60 s | 9/24 | 0/24 | Fourteen windows coarse-gated, one fails margin; sparse remaining evidence and no compatible seed survives cap. |
| 19 | 22.83 s | 21/23 | 0/23 | Adequate input, no compatible seed retained (best rank 975, cap 512). Alternative coarse-seeded curvature output recovers it. |
| 11 | 20.60 s | 11/29 | 11/29 | All available matching sources recovered. Fifteen windows coarse-gated, three fail margin. Three extra output sources are close to interpolated curve (≤338 Hz). |
| 59 | 20.37 s | 35/35 | 0/35 | Complete input, no compatible seed retained (rank 549). Both coarse and expanded alternative banks recover it. |
| 33 | 18.45 s | 27/30 | 0/30 | Adequate input, no compatible seed retained (rank 623). Both alternative banks recover it. |
| 54 | 16.08 s | 22/32 | 22/32 | All available matching sources recovered. Nine windows coarse-gated, one fails margin. |
| 7 | 14.60 s | 12/21 | 10/21 | Eight windows coarse-gated, one incompatible CFO; 4.29 s matching-evidence gap. |
| 35 | 14.42 s | 12/12 | 12/12 | No server points lost. Purity fails because ARM includes ten additional source points. All are within 231 Hz of interpolated server trajectory. Likely evaluator/reference incompleteness, not demonstrated ARM contamination. |
| 60 | 14.25 s | 4/21 | 0/21 | Fifteen windows coarse-gated, two fail margin. Four matching points are below minimum support of eight and include a 6.08 s gap. |
| 5 | 13.61 s | 8/17 | 8/17 | All available matching sources recovered. Eight windows coarse-gated, one incompatible CFO. |
| 61 | 13.07 s | 10/22 | 10/22 | All available matching sources recovered despite a 5.75 s gap between matching reference sources. Twelve windows coarse-gated; an additional output source may help bridge sparse reference support. |
| 62 | 11.42 s | 18/23 | 18/23 | All available matching sources recovered. Five windows coarse-gated; coverage is 78.3%, just below cutoff. |

The gap figures describe matching reference sources, not every candidate the
tracker might use to bridge a gap. They are diagnostic constraints rather than
proof that increasing the gap setting would recover a valid track. Similarly,
coarse-gate rejection identifies where evidence disappears, not proof that
unscreened GLRT would pass. The raw detector and source-level receipts support
these counts without rerunning IQ or changing thresholds.

## Seed-loss cross-check using existing alternative outputs

The previously executed, source-only coarse-seeded curvature bank was evaluated
with the same frozen membership thresholds. It contains 62 hypotheses versus
55 in the physical pair-seeded result, represents 49 server segments versus 46,
and adds exactly references 19, 33, and 59 without losing a previously represented
reference. One-to-one matches increase from 37 to 40. Native coarse seeds alone
contain 94 hypotheses and represent 42 references, including 33/59 but not 19.

This is corroborating evidence that those three losses are recoverable through
initialization. It is not a one-variable causal ablation: the hybrid uses a
different initializer and hypothesis bank. These alternative outputs were run
on the host, not newly qualified on physical ARM. They are overlapping
hypotheses, not exclusive satellite identities. No production change is made.

## Implications for correctness work

1. Fix initialization coverage first for refs 19/59/33: the detections already
   exist and an independently seeded alternative recovers all three.
2. Replay representative coarse-gated source windows, starting with long refs
   8/30/34/47, before attempting tracker tuning to replace absent evidence.
3. Review source-purity semantics using ref 35: absent server labels should not
   automatically make extra, curve-consistent ARM points contaminants. Keep
   the frozen strict score and a separate review assessment until validated.
4. Treat refs 2 and 62 as threshold-near coverage losses, and assess cautious
   gap bridging separately from physical identity continuity.

Ref 35 is **not** silently granted a second exception. Only ref 10 is excluded.

## Reproducibility and plots

Run `../review_remaining.py` after `../diagnose_missing.py`. It checks the 16-row
remaining inventory, writes the explicit exception receipt, evaluates both
existing alternative banks, and draws every remaining segment using measured
points. Original golden/scientific results and thresholds are preserved.

- `remaining-review.json`: all 16 source-level diagnoses joined to seed evidence.
- `coarse-diagnostic.json`, `expanded-diagnostic.json`: alternative membership results.
- [Longest eight](remaining-1.png), [remaining eight](remaining-2.png).
- [PDF page 1](remaining-1.pdf), [PDF page 2](remaining-2.pdf).
