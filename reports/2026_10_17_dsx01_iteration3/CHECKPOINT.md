# Iteration 3 checkpoint: recovery lead, goal still active

The previous goal turn produced the checked 15-window recovery table and
satellite timing histograms. This turn makes new numerical and modeling
progress: 40 new timing-prior fits with 20 verified reused controls; four
controlled provider fits; eight complete-state portfolio pilots; eight
training-only band-calibration pilots; and 20 frequency-width continuation
fits across all five sources. Bounded numerical finishing is separate. The
dataset remains 15 windows / 693 original winning observations across five
recordings / 20,084 original winning observations.

## Measured result

| Method, fitted-c | Window associations | ≥80% net-restored windows | Full associations | Lost original full support |
|---|---:|---:|---:|---:|
| Original | 96/693 | 0/15 | 11,222/20,084 | 0 |
| Exact profile, fixed candidates | 422/693 | 6/15 | 13,784/20,084 | 742 |
| Exact profile, expanded candidates | 434/693 | 7/15 | 14,248/20,084 | 791 |
| Fixed profile + extra 125 Hz continuation | 422/693 | 6/15 | 13,784/20,084 | 742 |
| Fixed profile + width continuation | 455/693 | 7/15 | 14,173/20,084 | 1,037 |
| Fixed profile, relative timing prior 1 s | 347/693 | 4/15 | 13,366/20,084 | 851 |
| Fixed profile, relative timing prior 0.5 s | 339/693 | 5/15 | 12,302/20,084 | 1,177 |
| Fixed profile, causal Space-Track | 371/693 | 5/15 | 13,793/20,084 | 925 |

Width continuation adds 33 window and 389 full-scan assignments relative to its
matched extra-125-Hz control. It has an extra 1,000-objective/120-second budget
after the original profile. Intermediate widths 1000/500/250 Hz are search
aids; final selection/classification uses the original 125 Hz objective.
The new state does not dominate expansion: there are more lost original
assignments, only two strict raw endpoints, and large position-reference
distances remain. Supplementary finishing preserves hard memberships; S02/S04
remain rejected. The scientific KKT threshold is unchanged.

Window 003 remains 0/27. The expanded and width-continuation methods restore
different seven-window sets. Do not take their union and claim eight windows
for a single algorithm. All 15 raw per-window outcomes, new/lost memberships,
paired RMS, timing and position diagnostics are in the [report](README.md).
The [findings](FINDINGS.md) explain the negative controls and model implications.

## What is now better understood

- Tighter timing priors alone reduce full-data recovery under matched search
  budgets, even while narrowing timing distributions.
- S02–S04 already used Space-Track. Replacing only the older S01/S05 HF elements
  cannot fix their bad warm geography/calibration basin by itself.
- Expansion's support losses are mostly substantial residual changes, not
  tiny posterior-threshold crossings, invisible satellites or missing old IDs.
- Genuine causal FAST calibration donors exist for S02–S05, but seeding only
  their band differences does not improve the measured S03 half-held test.
- Older 63/66-probe holdouts and whole-half temporal holdouts are different
  experiments. A faithful production cold replay needs a separate explicit
  discovery budget, held-time propagation bank and clock extrapolation policy.
- Multiple GLRT peaks are common (54,321 peaks / 20,084 groups), but best-of-peak
  counting can manufacture apparent recovery. Window003 has ten any-peak
  matches versus fourteen in a time-permutation control. No such matches are
  credited to the headline counts.

## Validation and preservation

Twenty-eight new component tests have passed in isolated module invocations:
ephemeris5, timing6, calibration4, wide-grid3, support-portfolio3,
annealing-model3, supplementary-polish1 and centred-arithmetic3. The existing
three bounded-polish engine tests also pass in the agent's ten-test numerical
suite. Exact row identities, source receipts, c=0 settings, query order and
budgets are verified in component receipts. All previous 600 sealed report
files are hash-verified unchanged (39 dataset + 283 model + 262 iteration2 +
9 first recovery snapshot + 7 latest recovery snapshot).

No RF acquisition, hardware command, production write, contract change, remote
push or unrelated tracked-file edit was performed. The pinned scientific
runtime and immutable original dataset remain the authorities.

## Next work already assigned

Three SOL agents continue in the new sibling directory
`../2026_10_17_dsx01_iteration4/`, preserving this checkpoint:

1. `expanded_annealing/`: apply width continuation after the existing generic
   expansion, with matched extra-125-Hz controls and a uniform all-five policy.
2. `peak_mixture/`: normalized latent peak identity per original probe, exact
   one-peak nesting, proper q/visibility normalizer derivatives and permutation
   controls. Evaluate original winners separately from group likelihood.
3. `frequency_bias/`: shared per-satellite constant-Hz residuals with explicit
   shrinkage, exact all-point signed bias profiles and b=0 nesting. Test as an
   empirical nuisance model, not an established hardware or orbit explanation.

See the [next protocol](../2026_10_17_dsx01_iteration4/PROTOCOL.md). No algorithm
may use station coordinates, target-window exceptions or manually chosen
satellites as seeds or selectors. All partial new outcomes remain research
evidence. Improved point counts do not complete the generalization objective;
the next successful candidate still needs excluded-data prediction and
position evaluation under a correctly reconstructed training-only pipeline.
