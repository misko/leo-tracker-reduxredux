# DS24: causal identity competition and generating-component controls

Date: 2026-10-25. This bounded iteration follows the
[fast-scan review](https://github.com/misko/leo-tracker-reduxredux/blob/main/reports/2026_10_25_ds24_next_directions_review/README.md).
Three SOL xhigh agents implemented the two experiments and independently audited
their inputs and results. The operational algorithm and its associations are
unchanged; these results do not constitute an ALGO promotion.

The new evidence sharpens two priorities. **Satellite identity needs an explicit
unresolved outcome**, because plausible causal alternatives remain nearly tied
for two of four new-family proposals. **Orbital timing/shape uncertainty deserves
priority over generic receiver flexibility** in the conditional fast simulator:
removing its generating deviations reduces mean error substantially, whereas
removing the modeled receiver deviations does not. Neither finding establishes
the cause of every real scan's error.

## What this adds to the accumulated evidence

The previous review documents the full experiment history and source reports.
The important distinctions remain:

| Previously tested direction | What it establishes | Consequence for the next work |
| --- | --- | --- |
| All channels versus either half, same 24 DS24 fast scans | Fitted-c mean error is 1.220 km for CH1–8, 1.558 km for CH1–4 and 2.040 km for CH5–8. | All channels already help on average; the question is why their incremental precision is limited. |
| Thirty targeted continuous-position restarts | Endpoints agree within 2.06 cm for the tested assignments. | Repeating generic multistart is low priority; discrete identity alternatives remain a separate issue. |
| More recovered native GLRT points on DS23 | Graph-to-native accepted coverage increases 70.71→74.41%, but fitted-c mean improves only 1.434→1.426 km and P95 worsens. | Count additional position information as well as points. These postfit coverage figures differ from DS24 likelihood membership. |
| Shared RX1 correction on 24 DS24 scans | Fitted-c mean improves 1.220→1.120 km, with 11 improvements, seven regressions and six fallbacks. | Freeze and test this candidate on a verified later block before promotion; the existing scans are development data. |
| Local information controls | Median weak-axis scale falls from 534 m to 110 m when orbital timing is treated as known, versus 386 m with receiver parameters known. | Timing is strongly coupled to position. These are unavailable-information controls, not achieved accuracy. |
| Receiver remeasurement and noise changes | Cleaner frequency measurements have not supplied proportional position gains. | A specific physical defect or missing constraint must motivate another measurement experiment. |

All usable DS24 fast recordings in that comparison use 10 MS/s. They cannot
identify a causal sample-rate effect. The nominal feed separation changes sky
coverage; it is not itself a measured angle of arrival or a spatial baseline.
The review also records unsuccessful soft-identity, temporal-mixture, phase
integration, prior-narrowing and held-family movement tests. They should not be
repeated unchanged.

## Broad causal identity challenge

The four chronological proposals are 0010/64023, 0011/58175, 0012/57743 and
0013/60108. We screened the original causal catalogue using each discovery
track at its saved c=0 parent position, then froze the nominee plus seven
alternatives. The pre-existing 0012/66259 alternative was explicitly retained.
The three additional 0013 tracks never nominated candidates.

Each exact comparison uses the same fixed parent position and calibration for
all candidates. All shortlisted families are removed from parent calibration
and predictive conditioning before comparison, preventing a previously fitted
alternative from receiving an asymmetric advantage. The cavity removes
280 curved and 62 predictive observations for 0010, 41 curved observations for
0013, and none for 0011/0012. All eight resulting parent states pass their saved
RF gates, phase convergence, precision convergence and support checks.

Candidate-specific causal timing priors, three physical-mode uncertainties,
shared receiver uncertainty, source constants and observation noise are carried
through the prediction. Whole-source aliases −4…+4 have the same uniform prior
for every candidate and the unresolved comparator. Direct nonlinear phase is
integrated, rather than replacing it with a fitted free slope. No position is
optimized and no evaluation GPS enters this branch.

The score below is negative twice log predictive density; lower is better.
Margins compare the best two shortlisted physical candidates under the same
parent state. They are not percentages or calibrated identity probabilities.

| Scan | Best / runner-up at c=0 | Margin c=0 / fitted-c | Interpretation |
| --- | --- | ---: | --- |
| 0010 | 64023 / 68298 | 475.555 / 481.919 | Clear separation inside this shortlist; no second raw owner found in the earlier audit. |
| 0011 | 58175 / 63312 | 0.384 / 1.289 | Newly discovered close competitor; identity remains unresolved. |
| 0012 | 57743 / 66259 | 1.422 / 1.344 | Fitted-c reverses the winner to 66259. Identity remains unresolved. |
| 0013 | 60108 / 56419 | 35.280 / 32.584 | Clear discovery-track preference, with additional whole-track prediction below. |

The 0011 margins correspond to only about 1.21:1 and 1.90:1 relative densities
for its best pair. The 0012 margins are about 2:1, with opposite preferred
identities. Parent position and calibration both differ across c arms; this
does not isolate the effect of c. Strong preference over a broad unresolved
polynomial does not distinguish two physically plausible satellites.

![Causal candidate competition at saved parent positions](identity/candidate_identity.png)

For 0013, condition on the original 53-point RX1 CH2 discovery curve and predict
each additional complete curve separately. All 189 native IDs are distinct and
excluded from both original accepted-ID ledgers.

| Held track | Points | Best satellite | Margin over runner-up c=0 / fitted-c | Gain over unresolved curve c=0 / fitted-c |
| --- | ---: | --- | ---: | ---: |
| RX1 CH4 T000 | 85 | 60108 | 35.411 / 38.901 | 53.182 / 55.741 |
| RX1 CH7 T004 | 36 | 60108 | 3.279 / 5.270 | 44.645 / 45.732 |
| RX1 CH8 T004 | 15 | 60108 | 7.065 / 12.225 | 52.790 / 54.013 |

This supports investigating 60108 jointly across channels. CH7 provides weaker
discrimination than CH4, and the overlapping conditional comparisons cannot be
summed as independent evidence. All four tracks are RX1, leaving a shared
receiver discrepancy possible. The candidate shortlist was selected using the
discovery source, and the unresolved comparator is a declared Gaussian
degree-four curve model, not an empirically calibrated clutter population.
The additional owners were found in archived proposals under the original
60108 identity: withholding them from this shortlist nomination does not make
their prior selection identity-blind validation.
Consequently no new identity is operationally accepted here.

![Additional whole-track predictions in scan 0013](identity/whole_owner_identity.png)

The complete sources, protocols, scores, figures and numerical limits are in
[identity findings](identity/FINDINGS.md). The screen and exact comparisons
completed in 78.89 s cumulative scientific wall time, within the fixed 600 s
cap, with two workers and one BLAS thread each. This branch performed no
position fits. Fixed parent-state evidence is not a global joint position-and-
identity search.

## Paired fast-scan component interventions

We reused eight previously frozen noisy realizations: two fast scan geometries,
two artificial positions, and two seeds. Each intervention preserves the
original remaining coefficient draws, native IDs, source constants, Gaussian
noise and Gamma precision. Both c arms receive identical observations. The
original 25×25 km region, cold start, inference priors, labels, gates and search
budget remain unchanged.

One intervention sets generating orbital time shifts to their causal prior
means and generating physical-mode coefficients to zero. Another zeros the
generating hardware/smooth receiver coefficients. Inference is not given these
true coefficients. This distinguishes the experiment from an oracle that fixes
nuisance parameters during inference.

| Generating condition | Mean error c=0 / fitted-c, km | Maximum c=0 / fitted-c, km | Improvements / regressions, each arm |
| --- | ---: | ---: | ---: |
| Original deviations | 0.460 / 0.469 | 1.059 / 1.094 | Reference |
| No orbital timing/shape deviations | 0.295 / 0.297 | 0.522 / 0.571 | 6 / 2 |
| No hardware/smooth receiver deviations | 0.468 / 0.474 | 1.122 / 1.152 | 3 / 5 |

![Every paired artificial-position result](synthetic/paired_component_errors.png)

All 32 new fits pass the original gates. Removing timing and shape together
reduces fitted-c mean error by about 37%, but two realizations worsen. Removing
the modeled receiver deviations does not improve the mean. The paired effects
depend on the realization and can reflect cancellation with retained components;
separate phase–shape effects remain unidentified.

This is evidence about a conditional simulator with known labels and inherited
selection, not proof of an actual orbit error in a particular recording. It
does not exclude receiver defects absent from the generating model, test
association errors, distinguish timing from shape, or establish a precision
floor. Errors still reach 0.571 km after the combined orbital intervention.

![Paired error directions](synthetic/paired_error_directions.png)

Frequency fit tells a different story. Mean c=0 curved RMS is 108.055 Hz in the
control, 108.040 Hz without orbital deviations and 107.972 Hz without receiver
deviations. The largest small RMS improvement accompanies no mean position
improvement. Raw scores across these different generated observations are not
same-data model comparisons.

[Synthetic findings](synthetic/FINDINGS.md) provide every paired outcome,
actual observation NPZ, latent/noise bindings, source hashes, gate replay and
independent audit. The fits used 57.15 s wall time; preparation through all
fixed replay checks used 221.19 s, under the frozen 600 s cap. No failed seed,
fit or regression was discarded.

## Next directions, in priority order

1. **Complete the timing-versus-shape diagnosis.** Add phase-only and shape-only
   generating interventions to the same eight realizations, with unchanged
   inference and noise. This completes a paired 2×2 component design with 32
   additional c-arm fits. It answers a missing question; another generic local
   phase integral or known-phase oracle would repeat earlier work. Do not
   narrow real priors based solely on this simulator.
2. **Develop an identity decision that can remain unresolved.** Use 0011 and
   0012 as explicit ambiguous cases and 0013 as the whole-track prediction case.
   Test the complete nomination-and-decision rule on declared plausible wrong
   satellites and unresolved sources before choosing an acceptance threshold.
   Carry timing/shape uncertainty into later position fits, preserve all old
   accepted IDs, and report movement separately from frequency fit. The present
   density margins alone are not a calibrated acceptance rule.
3. **Validate the frozen RX1 correction on later existing recordings.** This
   remains the strongest recent real-cohort mean candidate. A metadata inventory
   finds 32 later jobs, but has not established an untouched geographic holdout.
   First verify full public contracts, raw identities and previous error
   exposure; then freeze a chronological comparison with matched c arms and
   all failures retained. Do not retune on the new block.
4. **Spend recovery effort on new constraints.** After identity qualification,
   rank sources by their additional position sensitivity after timing, orbit
   and receiver uncertainty is accounted for. Compare against length/count
   ranking on an identical candidate set and search budget. Prefer independent
   geometry or useful time coverage to redundant points from the same uncertain
   family. Expected information allocates search effort; it does not certify
   identity.

These directions use existing single-scan RF and causal orbital information.
They do not require stationary receiver pooling, a moving-trajectory prototype,
postscan TLE inference, true-position selection or new radio collection.
Continue publishing negative results and individual regressions alongside means.

## Data readiness and replay limits

The frozen DS24 population remains 34 fast scans, 24 with previously evaluated
usable inputs. Nine original missing scans still lack matching source-session
contract metadata through the checked published path. DS24-0103 now has matching
10 MS/s contract metadata, but its current raw-authority hash differs from the
frozen manifest and must be reconciled before use. Thirty-two later automatic
jobs include 31 matching metadata records. Completed production position stages
do not by themselves imply geographic error was inspected.

The corrected [exposure audit](audit/EXPOSURE.md) explicitly supersedes an
initial filename-only lookup, since contract filenames encode run identities
rather than source sessions. It reads metadata only and establishes neither
full-contract validity nor a fresh validation cohort.

This report packages research code, derived outputs, actual new synthetic
observations, numerical audits and figures. It does not duplicate the complete
original scan/TLE banks or runtime environment. [Replay notes](REPLAY.md)
describe dependencies and the distinction between reviewing saved results and
rerunning the science. The preceding review remains the source for historical
comparison numbers. No new real-data position estimate, accepted association,
production component or ALGO release results from this iteration.
