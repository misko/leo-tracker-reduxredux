# Frozen fixed-position uncertain identity coupling

Use all eighteen original DS7/DS8/DS9 panels at q020 training-selected positions
and timings. Preserve all 4,328 distinct bank-eligible tracks, masks, candidates,
and the original training-horizon visibility gate. No correction, cone change,
new propagation or geographic fit. Pair membership comes only from the published
training-selected support census; candidate weights from that census are not
inserted as new likelihood evidence.

Each independent signal prior is uniform over its retained training-visible
candidates. The shared signal prior is uniform over equal catalogue rows in
both training-visible lists under the same pinned snapshot. Track-constant
offsets remain independently eliminated by the original Student-t4 contrasts;
this is assignment coupling, not frequency stitching or receiver calibration.
Given assignments, the two receiver likelihoods multiply. This explicitly assumes
conditional cross-RX noise independence; it does not establish physical independence.

Let q=.2 and rho be the coupling probability inside the both-signal component.
The five prior masses are (1-q)^2(1-rho) for independent signals,
(1-q)^2 rho for shared signals, (1-q)q and q(1-q) for the two mixed
signal/background states, and q^2 for both background. If the shared visible
intersection is empty, transfer its entire mass to both-background. Priors sum
to one in every case; the individual-track domain still requires a visible
candidate, as in the original model. Keep sigma=100 Hz and trend slope scale
2000 Hz/s. Pair joint-minus-training log density scores the held observations.

Freeze rho=0,.5,1. Preserve unpaired tracks independently and forbid duplicate
track use. Primary arms pair all selected pairs. For shuffled controls, restrict
both the selected and shuffled alternatives to the published non-singleton
control population; singleton tracks stay independent in both matched arms.
Report these matched comparisons separately from the primary full-population
ones. All original observations remain present in every arm.

Require zero-coupling training and held replay against the q020 donor to 1e-7,
including every individual track's training and held score. Nine tests cover
normalization of assignment and predictive densities, exact independent replay,
held isolation, swap symmetry, correct/wrong synthetic pairs, empty support,
namespace validation and no duplicated tracks. No held score chooses rho,
pair membership, bank contents or coordinates. Report every declared alternative.

One sequential child per panel, BLAS1/nice19, 90 seconds, 4 GiB address space,
and at least 5 GiB available RAM. Freeze all sources and inputs before launch;
retain failures without retries. Held prediction here is descriptive conditional
model evidence from previously explored data, not a blind identity validation
or a geographic accuracy estimate. No RF, raw IQ or provider/archive reads.
