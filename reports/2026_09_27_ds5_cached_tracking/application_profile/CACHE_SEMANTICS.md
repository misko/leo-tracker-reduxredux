# Cache semantics for scanner GLRT-64

## Finding

Past signal coordinates cannot replace blind acquisition while preserving the
current repository's full `analyze_glrt64_dwell` response. The safe exact cache is geometry and
content-derived work: immutable templates, grids, rotation tables, FFT plans,
scratch layouts, and carefully validated intermediate results from the same IQ.
A past epoch/CFO is a proposal for an approximate acquisition path, not an
exact cache hit.

A separate exact opportunity exists for the narrower `detect_first_glrt64`
contract. It can return after completing the probe that first establishes a
confirmation. It must still finish both receivers and every retained candidate
in that probe. This does not shorten `analyze_glrt64_dwell`, whose response
contains the complete probe schedule and final maximum margin.

## Application semantics that must be preserved

For the current 120 ms dwell, 20 ms probe, and 10 ms stride, the scanner
evaluates 11 overlapping probes. With two receivers and ten retained
acquisition candidates, the complete ceiling is 22 independent probe/receiver
acquisitions and 220 candidate confirmations. The current repository detector does the
following in order:

1. Copy one 20 ms receiver probe and independently run the full symbolwise
   epoch/CFO acquisition with fixed five-sample epoch and 10 kHz CFO
   nonmaximum-suppression distances.
2. Score every retained candidate independently with
   `conditioned_glrt64_score`. The live margin gate is
   `margin >= configuration.glrt64_margin_gate`. The current response contains
   integer acquisition epochs and does not report fractional timing refinement.
3. After both receivers are complete for a probe, sort passing hits by receiver
   and descending margin. A hit confirms only against an earlier hit from the
   same receiver whose probe starts at least 20 ms earlier and whose tracking
   CFO differs by at most 8 kHz.
4. Return the earliest compatible prior hit, not the current confirming hit.
   `decision_best_margin` is the maximum observed after all candidates on both
   receivers in the confirming probe have run. The full analysis continues and
   `full_best_margin` covers all 11 probes.

Consequently, exact equivalence means equality of the entire ordered probe and
candidate response, including ranks, integer epoch/CFO fields, scores,
pass flags, first detection, both best margins, and reason. Equal active/no
detection labels are insufficient.

## Exact reuse boundary

| Reuse | Exact status | Conditions |
|---|---|---|
| Qin exact/control templates, symbol indexes, frame-offset tables, CFO grids, fixed rotation banks | Safe | Key by rate, edge, symbol roll, probe length, acquisition configuration, and implementation/template version; expose immutable arrays. Several geometry/rotation inputs are already `lru_cache` entries in the current `templates.py` and `acquisition.py`. |
| Native/FFTW plans and scratch geometry | Safe | Private mutable workspace per concurrent worker; serialize planning/destruction when required; reset every input-dependent buffer. |
| Whole probe or dwell response for identical IQ | Safe but mainly useful for re-analysis | Content-address by IQ bytes plus receiver mapping, rate, edge, calibration, complete configuration, template hash, and detector code/version. Verify the cached serialized response hash. Live captures will rarely hit this cache. |
| Work shared by the 10 ms overlap inside one dwell | Potentially exact | Index intermediates in absolute dwell coordinates and reproduce the oracle's frame inclusion, phase origin, normalization, reduction order, tie breaks, and rank order. A full-dwell FFT or rolling sum is only exact after bit-level response equivalence; mathematical equality alone does not protect threshold and tie behavior. |
| Evaluate independent probe/receiver work concurrently, then fold decisions | Exact if results are unchanged | Reconstruct probe/receiver order before applying history and maxima. The decision fold remains serial and deterministic. |
| Prior epoch/CFO used only to choose evaluation order | Exact only if the same ten blind candidates are still produced and fully scored | Reordering cannot change nonmaximum suppression, rank, ties, response order, or omit work. This offers little acquisition saving. |
| Prior epoch/CFO used to narrow or replace acquisition | Approximate | It can miss a new signal, select another simultaneous branch, alter the ten-candidate list, and change both the full response and the first confirmed detection. A successful local GLRT does not prove that the blind winner or earliest confirmation is unchanged. |

The half-overlap does not make adjacent probe coordinates identical. Ten
milliseconds is 7.5 Starlink frame periods, so an epoch transferred to the next
probe must use the absolute source-sample lattice and a half-frame phase shift.
Resetting phase at each probe or adding the integer stride modulo a rounded
frame length is not exact.

Any causal proposal cache also needs at least
`(session/continuity epoch, channel, edge, receiver, rate, tuning/calibration)`
in its key. State cannot cross a retune, counter reset, rate or edge change, or
receiver. A single entry per key is inadequate when multiple pilot trajectories
are present; a bounded track bank with explicit association is required even
for an approximate design.

## Evidence against treating a tracked proposal as an exact cache

The frozen new-development V6 replay contains 256 receiver visits and 129 FP64
reference positives. Its cache/full-blind combination also returned 129
positives, but only 120 associated with the reference: nine reference positives
were lost and nine different positives were added. Within the 74 accepted
cache cases, only 65 associated; the other nine were branch substitutions. The
overall measured speedup was 1.80x, while the accepted-cache subset alone was
about 9.2x. The fast subset therefore does not satisfy an identity-preserving
application contract.

The receipt-only failure audit found 52 failed predictions. Only 24 were within
the 2 microsecond/8 kHz association gate, two were inside the declared
half-sample local-correction envelope, and three were inside its three-cell
probed span. Twenty-eight were outside association. Among the 38 failed
predictions that were reference-positive, 16 were outside association. A small
local correction around one past trajectory cannot recover the general case.

These figures are development diagnostics, not physical identity truth. They
do demonstrate that equality of positive counts and successful local
confirmation do not preserve the frozen reference branch.

## Exact decision-only early exit

`detect_first_glrt64` currently delegates to the full analysis and discards its
complete probes. A specialized streaming implementation can preserve its
three-field return contract exactly:

- process probes, receivers, acquisition candidates, scores, and hit sorting in
  the same order;
- after a probe's complete hit/history fold sets `first_detection`, return that
  prior hit, the already fixed `decision_best_margin`, and the existing positive
  reason;
- run the full schedule on every negative dwell.

The earliest confirmation is probe 2 because probes 0 and 1 overlap the current
20 ms window. In that best case the limited API evaluates three rather than
eleven probes: 60 rather than 220 candidate slots at the ten-candidate ceiling,
a 72.7% ceiling reduction in probe/candidate work. Later confirmations save
less, and negatives save nothing. This optimization cannot be used by the
standard scanner report path as currently structured because
`standard_analysis.py` calls `analyze_glrt64_dwell` and persists every probe.
Splitting an early live decision from later complete metrics would be a new
application contract with separate publication and failure semantics.

## Required qualification

An exact reuse implementation should compare serialized full responses against
the unchanged scalar oracle, with zero field differences, on:

- cold starts, expired/reset counters, retunes, and every cache-key change;
- real negative/quiet visits, constructed noise and tones, and near-threshold
  margins on both sides of the inclusive gate;
- both rates and edges, both receivers, physically fractional injected epochs
  including the frame seam, CFO near zero and near +/-399 kHz, and off-grid CFO;
- one persistent pilot, two close/equal pilots, branch crossings, a pilot plus
  a stronger tone, signal appearance/disappearance, and different simultaneous
  signals on the two receivers;
- first confirmation at probe 2, late confirmation, no confirmation, multiple
  compatible priors, and competing receiver/current-hit order in one probe;
- candidate nonmaximum-suppression and score ties, including values within a few
  floating-point units of the margin and 8 kHz gates.

The decision-only early-exit variant additionally needs exact
`DwellDetection(first, best_margin, reason)` equality against the full oracle
for every case, plus proof that it never exits before both receivers and all
candidates of the confirming probe finish.

An approximate tracked-acquisition experiment must be reported separately. It
should use causal top-K state, expose cold/expired/wrong-cache fallback, retain
all multiple-signal hypotheses, and report lost and additional branches rather
than interpreting a cache-confirmed proposal as the unchanged first detection.

## Audited evidence

- Current repository `src/leo/scanner/detector.py`: `01c21e7b138bc66c84efc341fff94d7938d18ed04ef9961286d4cabe73879270`
- Current repository `src/leo/scanner/models.py`: `6342bd529953d7340dcaf3403472d85ee04d03aecdb735b4b95d04cb59d83732`
- Current repository `src/leo/scanner/standard_analysis.py`: `36881a862a51de3e8942ff29534e5327498cb227873ca3adb7e4fa483d848ef8`
- Current repository `src/leo/analysis/starlink/acquisition.py`: `b4891b7ceb7f60a8d23c7e8127b836159a48aa5a2e2f0245e25ac26bd96d3742`
- Current repository `src/leo/analysis/starlink/pilot_methods.py`: `d6a599d7eb9cb4d6de5f7e6781cb6ea3ce65de422723d94ebfec9ea0a1fa4193`
- New-development V6 receipt: `b339bc15a7102f0405af9a9b340b3b4acaea3c18d3bb327053ba208514a365f9`
- Cache-failure diagnostic: `71165dcd3131c462f7c7ddd4744bc74229e237c49c32f12743b6efb14df3cbf2`
