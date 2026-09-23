# Independent phase test: candidate geometry predicts the CFO arc, phase adds no gain

On the frozen random holdout, the phase candidate has **79.67 Hz circular RMS**
versus **78.72 Hz for the GLRT candidate**. Both predict much better than the
constant-rate and wrong-time controls, but phase does not improve the matched
GLRT result. Their selected satellites differ and their receiver sites are
373.7 km apart. Against the user-provided receiver reference, the phase selection
is also farther away: **342.2 km versus 235.1 km**. This experiment does not
establish stronger satellite association, position accuracy, or orbit velocity.

![Frozen acquired-only held comparison](figures/2026_09_23_independent_phase/v2/held-comparison.png)

## Frozen comparison

The [revision 2 protocol](2026_09_23_independent_phase_v2_protocol.md), model,
measurement code, tests, and training qualification artifacts were committed
at `3f565e4f` before held IQ was opened. The selected source is the 40.8154-second
2.5 MS/s RX1 arc in `scan-hop-85afa91453f8847b`. The split is seeded random
whole-dwell assignment, stratified across three time regions: 15 training and
12 held, with no chronological holdout. The 19 originally reserved observations
and separate long-cohort validation/test recordings remain unopened.

Both arms search the same 880 causal candidates and 398 sites on the regional
50 km grid. They receive one offset and one linear receiver drift, with equal
training-dwell weight. Cached states screen 16 finalists per arm; exact nominal
SGP4 reranks them and predicts every held frame. Training geometry must be above
the horizon. This is a finite candidate/site screen, not a globally established
orbit or position optimum.

Only the original acquired CFO seeds the held waveform extractor. The held
GLRT, refined, and dealiased frequencies do not choose a response branch or
alias. Source timing and historical track construction remain inherited
conditions, so this is not blind discovery. Eligible odd-symbol pilot estimates
in groups 1, 2, 4 form a common response for every frozen model. Eligibility
comes from even-symbol support; odd boundary values are retained and no outliers
are removed.

The response is scored modulo RF_scale × 113,636.364 Hz using a fixed 250 Hz
wrapped-normal estimator-coordinate score. It is not a raw-IQ likelihood or an
absolute frequency/alias measurement. Frame scores average within dwell, then
all dwells receive equal weight. All **12/12** held dwells are covered, with
**130/144** eligible odd-frame opportunities, 8–12 per dwell, no abstentions,
and no odd search-boundary responses.

| Frozen model | Held circular RMS, Hz | Held mean negative log score |
|---|---:|---:|
| GLRT candidate | 78.719 | 6.489973 |
| Phase candidate | 79.666 | 6.491173 |
| GLRT wrong-time geometry | 577.182 | 9.105515 |
| Phase wrong-time geometry | 565.626 | 8.999858 |
| GLRT constant frequency rate | 927.384 | 13.320724 |
| Phase constant frequency rate | 922.469 | 13.247997 |

Lower is better. The primary score gain for phase over GLRT is −0.001199,
with descriptive paired whole-dwell bootstrap 95% interval
**[−0.015731, +0.016309]**. There is no incremental gain. The phase candidate's
gains over its constant and wrong-time controls are +6.756825
[4.300839, 9.569055] and +2.508686 [1.805583, 3.145254], respectively. The GLRT
candidate also beats both controls. These intervals use the predeclared 10,000
resamples and seed 20260925; they do not select a variant or establish population
generalization from one arc.

## Position and association interpretation

| Arm | Selected NORAD | Selected latitude | Selected longitude | Reference error, km |
|---|---:|---:|---:|---:|
| GLRT | 59785 | 37.730959 | −119.813800 | 235.143 |
| Phase | 58985 | 40.829901 | −121.494400 | 342.237 |

The coordinates were frozen before the [evaluation-only antenna reference](evaluation/2026_09_20_scanner_antenna_reference.json)
was read for this post-selection diagnostic. Horizontal errors use the spherical
haversine distance with Earth radius 6371.0088 km. The reference is user supplied;
survey uncertainty and altitude are not provided. No reference error was used
to refit or select a model. This post-hoc diagnostic is separate from the
predeclared circular held endpoint.

The frozen grid contains a site only **22.62 km** from the reference, yet the
selected sites are 235–342 km away. Grid spacing limits resolution, but the
error here also reflects candidate/site selection: the search did include
the reference neighborhood. A finer grid alone is not established as a remedy.

The two candidates can produce nearly the same short-arc frequency prediction
after receiver offset/drift fitting while assigning different satellites and
locations. The good control contrast therefore supports time-dependent orbital
shape in this inherited source arc, but does not uniquely identify its satellite
or receiver site. The fitted drift is a receiver nuisance coefficient, not
satellite acceleration. Lower training error does not settle the ambiguity:
phase training RMS was 53.63 Hz and GLRT training RMS 66.69 Hz, but their held
results are essentially tied and phase's position is worse.

## Why revision 1 failed, and what the correction means

The [first training fit](2026_09_23_independent_phase_training_audit.md) used a
227,272.727 Hz correction and retained two approximately 113.6 kHz jumps.
The actual even/odd estimator samples every second 4.4 µs symbol, so its fixed
symbol-matrix likelihood repeats at half that frequency interval. Revision 2
uses that lattice to align **training** even means with their prebound GLRT
gauge; held measurements receive no GLRT-based alignment.

The [three-visit branch qualification](figures/2026_09_23_independent_phase/train-branch-qualification.json)
and [all-15 training audit](figures/2026_09_23_independent_phase/train-all-branch-qualification.json)
also show why this cannot be called physical alias resolution. Re-extracting
raw IQ at acquired ± 113,636.364 Hz changes the NCO and tone solves. Compared
with acquisition, support masks change on two dwells for the negative shift
and three for the positive shift; same-mask modular CFO differences reach
103.38 Hz. No shifted branch was selected for the held experiment. The
acquired-only rule was fixed before its held results were available.

## Implications for phase-assisted tracking

The phase estimator produces usable held waveform evidence, and the orbital
models predict frequency curvature that a constant-frequency-rate model misses.
That comparison alone does not prove the curvature's physical cause. This
test does not justify replacing GLRT CFO with phase CFO or claiming better
association/localization. It demonstrates the need to distinguish waveform
precision from satellite/location identifiability.

The reported array axis of “79deg east” remains an operator observation with
baseline-versus-pointing interpretation unresolved. Calibrated inter-receiver
phase geometry could add a transverse-motion projection, as described in the
[observability audit](2026_09_23_phase_geometry_observability_audit.md), but this
single-receiver CFO comparison supplies no such projection. Establishing
direction and relative speed still requires the appropriate baseline, wiring,
receiver phase stability, and source/phase-branch evidence. No new RF collection
or production estimator change was made here.

This one 2.5 MS/s result cannot rank sample rates. The earlier
[2.5/10/15 MS/s pilot study](2026_09_23_source_seeded_phase.md) and
[15 MS/s long-arc controls](2026_09_23_longarc_phase.md) used different captures
and conditions. Further method development must preserve those distinctions
and use newly frozen random evaluation rather than tune this now-exposed holdout.

## Reproducibility

- [Frozen model](figures/2026_09_23_independent_phase/v2/training-model.json), SHA-256
  `185ccc2413e0f14fb05baf7d22deeb786cf465437cf229fc0067647ca06d6187`.
- [Canonical held frames](figures/2026_09_23_independent_phase/v2/held-frames.json.gz),
  [scores and all 12 responses](figures/2026_09_23_independent_phase/v2/held-evaluation.json),
  [paired comparisons](figures/2026_09_23_independent_phase/v2/paired-comparisons.json),
  and [position diagnostic](figures/2026_09_23_independent_phase/v2/position-diagnostic.json).
- [Acquired-only extractor/scorer](../tools/research/evaluate_independent_phase_v2.py)
  and [report generator](../tools/research/summarize_independent_phase_v2.py).
  Model and measurement sources remain unchanged after the freeze; the report
  generator subsequently adds the explicitly post-hoc position diagnostic.
- Twenty-two focused tests pass. Independent review checked the frozen hashes,
  exact held population, common response masks, and absence of reserved IQ reads.
