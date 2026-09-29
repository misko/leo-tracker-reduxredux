# Next: test residual agreement before applying a correction

Proposed follow-up, not executed here. Training-weighted donor support is
substantial enough for a bounded DS9 diagnostic, but not for a general three-
dataset correction. Keep all targets in geographic denominators; unsupported
targets must retain the baseline rather than borrowing future information.

1. Enumerate the supported catalogue candidates and their donor-group/target
   memberships. Retain the posterior mixture and signal responsibilities;
   conditional MAP agreement is not verified identity. Identify which DS9
   early/middle/late targets are covered, especially whether late DS9's large
   error has meaningful support. Inspect source element revisions and elapsed
   time rather than assuming a satellite residual remains fixed across passes.
2. At the frozen donor-only positions/timings, export training residual shape
   for those candidates. Compare within-candidate agreement across independent
   groups with receiver/RF and shuffled-candidate controls on matched donors.
   Use canonical frequency units, remove track constants consistently with
   the contrast likelihood, and report short/weak tracks explicitly.
3. Freeze a physically interpretable correction basis and limits only after
   inspecting the available inputs and existing residual models. A frequency
   slope and an along-track/timing-like displacement are different hypotheses;
   neither should be called a calibrated orbit or oscillator correction.
   Donor location error can contaminate either estimate and must remain a
   stated limitation. Do not fit using target held observations.
4. Require transfer evidence against the unchanged model and matched
   receiver/RF controls before any target geographic fitting. If that fails,
   stop this correction direction without tuning against reference error.

For targets without donor support, a distinct possible direction is an
independent waveform-quality contribution to the track contamination prior.
This would change evidence about whether a track is satellite-like, rather than
repeat the failed pilot-frequency point-refinement experiments. Before fitting,
audit whether existing pilot/known-symbol features come from baseline training
visits and whether feature selection inspected held visits. Missing or weak
pilot evidence must not be silently interpreted as non-satellite truth. The
existing all-track symbol census has only short excerpts and no decoded
satellite identifier; its unsurveyed clustering cannot provide identity labels.

This secondary direction is unexecuted and needs its own frozen controls,
including rate/RF/SNR confounding, coverage, and held-visit isolation. It is not
permission to rerun failed pilot-frequency variants or undertake a new RF
campaign. Work remains on the existing corpus.
