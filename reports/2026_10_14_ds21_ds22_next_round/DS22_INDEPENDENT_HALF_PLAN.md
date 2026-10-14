# Independent half controls: first DS22-001 pair

The existing low/high results share all-channel discovery, candidate unions,
geographic proposals and some receiver lifts. They are useful conditional
comparisons, but do not establish performance of an independent four-channel
pipeline. The first new experiment is one lower/upper pair on DS22-001; no
broader half campaign is proposed before that pair is qualified.

The private `tools/ds22_independent_band.py` port returns a single explicitly
scoped preparation object. It has no `all/low/high` mapping and returns neither
the full source nor the split object containing opposite-band/held probes.
Genuine DS22 frozen membership, source digest and development-role gates precede
loading. The original seed 20261012 and 20-second counter-block split are
computed from common metadata, then only the chosen training-band probes are
projected. TLE temporal eligibility and geographic prior stay matched. The
full counter envelope is metadata, not a numerical all-channel proposal.

Two new exclusive namespaces will bind `low` = CH1–4 and `high` = CH5–8, their
exact prepared evidence, independent candidate selections and complete lineage.
They must never accept the shared discovery terminal or six-proposal export as
their numerical parent. No existing frozen source or public contract changes.

1. Freeze the private band policy, inventory, original source, TLE snapshot,
   counter partition and own source archive. Qualify both preparations with
   zero optimizer/orbit calls inside the original 60/75/80-second bounds.
   Component tests alter opposite-band candidate frequencies and require
   byte-identical selected-band evidence, while selected-band evidence changes
   when its own frequencies change. Held probes must never be projected.
2. Implement a narrow discovery consumer over `BandTraining.prepared` directly.
   Reuse the original grid, 100-point maximum, fixed candidate eligibility and
   training-only selector. Each band receives its own 480/495/500-second slice0
   and independent bank/point receipts; continuation needs explicit checkpoint
   review. The bank may share deterministic orbital eligibility, but candidate
   ranking, point scores and geographic proposals use only that band's data.
3. Reuse the original shape/bootstrap/cold numerical functions through
   explicit single-prepared-data ports. All proposals, nuisance coefficients,
   calibration frames and receiver lifts derive solely from the selected band.
   Preserve six starts per model with a prespecified within-band recipe:
   three cold starts and three shape-derived starts, ranked/deduplicated by
   training objective only. Do not fabricate three view names or duplicate
   a single seed to satisfy a legacy three-view aggregate validator. Pin that
   recipe before any location fits; if the existing math cannot produce six
   distinct seeds under the matched discovery budget, report the limitation
   and retain available starts rather than borrowing opposite-band seeds.
4. Fit B and C independently in each band's own calibration frame using original
   fitted-c math and six-start/20-second/600-iteration/25-km limits. A is a
   sequential two-band model and has no meaningful standalone half version.
   Compare all-channel A/B/C against explicitly identified independent B/C
   half baselines, as well as existing shared-initialization half results.
5. Seal all outcomes before the existing configured-reference comparison.
   Keep DS22 station-continuity uncertainty visible. Report convergence,
   failures and wall time separately from distance; do not select models or
   starts from reference error. The completed implementation and first-pair
   result are recorded below.

The first-pair consumer and six-start recipe were reviewed before source freeze
and real preparation. The seven-case full-channel DS22 matrix is complete.
Final dataset acceptance still requires paired
independent controls on the frozen eligible development set, with unavailable
members retained and locked members untouched until release.

The first actual independent DS22-001 preparations subsequently passed their
zero-fit qualifications: lower 26.299 seconds, upper 17.254 seconds, each with
407 frozen sources and zero optimizer/orbit/reference/held activity. Lower
contains 1,811 windows and upper 1,418. Their independently reconstructed
evidence digests exactly match the original conditional half preparations,
confirming the data partition is controlled while discovery and initialization
are being separated. The preparation protocol digests are
`858e8103a32cae6db2dd97caca400a0c022b4ef20af3cda0e23456c8064fd778`
(lower) and
`70bdd8857a27c4706f97994926f0410f8ee7c87bed8c2f713ce6915b36a8bdf8`
(upper).

The scoped discovery facade and durable point validator were reviewed and
committed as `17148ed4d`; the combined preparation/discovery component suite
passed 20 tests in 6.16 seconds. Its first lower/upper slice-0 discovery runs
completed all 100 points on slice 0 in 130.008 and 122.149 seconds respectively,
under 480/495/500-second bounds in separate namespaces. Each
point claim binds its own frozen protocol, prepared evidence, bank and source
archives. A cached reader cannot rebuild a missing bank or retry an orphan.
The downstream native evidence port receives only scoped training tracking
candidates and derives receiver lifts separately in the same scoped frame.

## Hybrid dependency audit and prospective initializer recipe

The independent initializer omits the intermediate hybrid fits. This is a
prespecified single-band recipe, not an isolated channel-only ablation of the
full pipeline: its initialization compute budget and completion gates differ.
The full pipeline's hybrid receipts remain preserved and counted.

The exact existing numerical consumers establish why omission does not discard
a seed refinement used by the final models:

- `ds21_fitted_initialization.stage_proposals` obtains cold proposals directly
  from the original discovery selections and six proposals from those cold
  points plus the shape-bootstrap pool. It never reads hybrid fitted vectors.
- `ds22_fitted_initialization.read_stage` changes candidate indices only at
  shape-bootstrap through `fresh.candidate_union`. Hybrid passes the frozen
  candidate pool through unchanged. Its terminal requires completed call
  receipts and valid aggregate selection, but `hybrid_result` explicitly
  permits `selected=None`; no converged hybrid winner gates later eligibility.
- `ds21_fitted_initialization.assemble` builds cold fallback timings from the
  nearest shape-bootstrap seed, then exports the cold and shape-bootstrap
  seeds with `encode_initial_physical_seed`. Hybrid contributes only its
  `hybrid-result.json` report. The independent equivalent must use its own
  band's shape donors, never the full pipeline's `seeds/all.json` donor.
- `ds21_fitted_models_v2` derives Model C receiver branches from the final
  exported physical entries with `physical_receiver_branches`; neither hybrid
  results nor their winner eligibility enter that calculation.

The removed stage therefore supplies a receipt-completion/physical-validity
gate, not numerical proposals, candidate eligibility, final seed values or
receiver lifts. A claim that all scientific budgets are identical would still
be incorrect. The new consumer will record actual scoped shape attempts,
bootstrap calls, selected starts and shortages explicitly. Its first pair
remains conditional on this independent single-band initialization recipe.

## Qualified first-pair execution

The initializer implementation (`68a1d9d24`) passed 13 component tests, including
real scoped physical projection/export through JSON receipts, source-kind
lineage, opposite-band donor rejection and candidate/shortage/nuisance mutation
checks. Both first-attempt initializers are complete with six distinct physical
starts each. Lower retained 36 candidate satellites and upper 28; the existing
shared full-channel initializer retained 46. All three shape attempts in each
band were stationary, and all twelve subsequent bootstrap calls succeeded.
No failed fit was retried or numerical source changed after freeze.

The 412-source initializer protocols passed zero-fit qualifications in 7.723
seconds (lower) and 6.556 seconds (upper). Subsequent stage times in seconds:

| Band | Shape | Shape bootstrap | Cold bootstrap | Physical export |
|---|---:|---:|---:|---:|
| CH1–4 | 9.586 | 13.462 | 11.886 | 7.873 |
| CH5–8 | 7.029 | 11.661 | 8.509 | 7.450 |

The independent B/C consumer (`366b85097`) passed nine component tests, including
actual wrapped B and native C objective construction from public single-band
training inputs. Each native model retained zero temporal edges and zero
measured waveform evidence, matching the original neutral singleton model.
The B common clock and C original no-common-clock structures are preserved.
Receiver ambiguity lifts are derived separately from each band's own native
observations and physical seeds; no all-channel lift enters either control.

Both 422-source model protocols passed mandatory zero-fit qualifications in
17.480 and 14.086 seconds, followed by successful physical initialization in
21.894 and 14.688 seconds. The 24 prescribed final fits (six starts × B/C × two
bands) ran on two workers with original fitted-c 20-second,
600-iteration, 25-km limits and durable per-start claims. They subsequently
completed and sealed before the comparison below. Nonstationary outcomes remain
unavailable under the original stationarity test.

The separate post-seal evaluator (`c8c64c9eb`) passed three component tests. It
requires both existing complete seals before reference access, preserves
unavailable model selections, pins explicit reference/source bytes, and never
sets an accuracy-target achievement flag while station continuity is unconfirmed.

## Completed independent pair versus original shared-initialization baseline

Both matrices completed all twelve prescribed final fit calls and sealed on
the first attempt. Each had eleven stationary fits. Lower C-start2 failed the
unchanged stationarity threshold with KKT residual 0.00266532 after 8.693 seconds;
upper C-start2 had residual 0.00278931 after 4.197 seconds. These were solver-success
results rejected by the original `1e-3` acceptance threshold, not timeouts.
They were neither accepted nor retried. All twelve B fits were stationary.

The following values are distances in km to the **configured, unconfirmed**
station reference, not verified DS22 position accuracy. All selections were
sealed training-objective minima before reference access. The all-channel and
shared-half columns are the original DS22-001 model matrix, unchanged by this
experiment.

| Model | CH1–8 original | Shared CH1–4 | Shared CH5–8 | Independent CH1–4 | Independent CH5–8 |
|---|---:|---:|---:|---:|---:|
| B | 0.785018 | 3.555036 | 6.439582 | 17.445828 | 10.874567 |
| C | 21.266493 | 23.645468 | 12.163078 | 11.239025 | 5.009017 |

B using all channels is closer to the configured reference than either genuine
independent half on this sample. C using all channels remains farther than both
independent halves. Independence worsens B's half results but improves both C
halves relative to shared initialization. This establishes that the earlier
shared-half comparison was insufficient to characterize independent pipelines;
it does not identify which of candidate selection, geographic initialization,
calibration transfer or receiver lifts causes the change. This first pair is
not a dataset-wide accuracy result, and no 0.5-km target is claimed.

The independent lower/upper candidate pools overlap in 18 satellites. Five lower
and three upper candidates are absent from the original shared 46-satellite
pool; conversely, that shared pool has 15/21 satellites absent from the lower/upper
independent pools. The candidate/pipeline differences and omitted unused hybrid
stage mean this comparison is not a single-variable channel ablation.

Actual final optimizer time was 46.560 seconds lower and 26.831 seconds upper;
the twelve unit wall times summed to 273.687 and 217.716 seconds respectively.
Repeated source/preparation checks dominate the difference. No live job remains.

Artifacts:

- Initializers: `local/ds22-independent-band-initialization-v1/DS22-001/{low,high}`.
- Model matrices: `local/ds22-independent-band-models-v1/DS22-001/{low,high}`.
- Post-seal comparison: `local/ds22-independent-band-comparison-v1/DS22-001`;
  protocol SHA256 `e06db18616278b57b37aa47ac179d4ae33ae4f22fa01c58fa980a5bc4580f6d8`.
- Full baseline: `local/ds22-configured-comparison-v1/DS22-001`.

The reporting reference source remains pinned to SHA256
`6de071077d8c2fe11a991b665c50edaf728ef9ffd320dca36cfedc44ee874bf9`.
The comparison explicitly sets `target_accuracy_claim_permitted=false`.

## DS22-003 replication and selected-lift audit

The next authorized pair used exactly the frozen pipeline, without source edits
or retries. Both discoveries completed 100 points on slice 0 (lower 131.578,
upper 79.924 seconds). Each initializer produced six distinct physical starts;
their candidate pools contain 42 and 25 satellites. Both model matrices sealed
all twelve calls, with **24/24 stationary** fit outcomes across the pair.

Distances below retain the same configured-unconfirmed reference limitation:

| Model | CH1–8 original | Shared CH1–4 | Shared CH5–8 | Independent CH1–4 | Independent CH5–8 |
|---|---:|---:|---:|---:|---:|
| B | 1.819243 | 2.809257 | 2.828654 | 34.689424 | 1.350193 |
| C | 2.827544 | 4.132040 | 1.642876 | 3.518443 | 1.663814 |

On DS22-003, each original full-channel model is farther from the configured
reference than its independent upper-band control, and closer than its
independent lower-band control. The lower B control's large change also shows
that shared initialization can materially help a half-band result. No seed was
chosen by these distances. The selected independent C starts are both index 0;
their training coordinates in the common regional frame are
`[-83.5251835217225, -80.75503595458517]` (lower) and
`[-85.44271249253627, -81.471072270812]` (upper).

The complete artifacts use the same private namespaces with `DS22-003`;
comparison protocol SHA256 is
`d9519a6ea93dd3dcd237cf292985004987f1a8fdfa80b3fd39a6c822600ecddb`.
DS22-019 has now completed both independent matrices, as reported below.

A separate receipt-only check on DS22-001 found identical selected receiver
ambiguity integers in shared C-all/start2, shared C-low/start2, shared
C-high/start5, independent C-low/start0 and independent C-high/start3:
receiver 0 = −1, receiver 1 = +2. Therefore different selected receiver-wide
integer lifts do not explain that sample's improved independent C halves.
Candidate pools, geographic/timing seeds and continuous physical corrections
still differ, so this is not a general causal exclusion of lift derivation.

## DS22-019 completed independent controls

Both discoveries completed all 100 points in their first slice (91.30/85.41s).
The lower initializer supplied six starts and 43 candidates; the upper supplied
five starts and 22 candidates because one shape attempt was not stationary.
The shortage was retained without replacement or retry. All 22 planned final
B/C fits were stationary, and both matrices sealed before comparison.

Distances below are kilometres to the existing **configured, unconfirmed**
station reference, not verified position accuracy.

| Model | Original all | Shared lower | Shared upper | Independent lower | Independent upper |
|---|---:|---:|---:|---:|---:|
| B | 113.239 | 166.428 | 154.377 | 133.061 | 275.894 |
| C | 142.114 | 203.397 | 214.751 | 137.918 | 278.676 |

The comparison protocol SHA256 is
`8b1b72f55c01a97ef2e99722188c5f6cd390f012d6b7a49dc553d4e2f584ccb1`.
No target-accuracy claim is permitted. The independent recipe's omitted unused
hybrid stage and differing initializer budgets remain an explicit limitation.

## Reference-free basin audit: different causes on 001 and 019

The sealed audits under `local/ds22-independent-basin-audit-v1/DS22-{001,019}`
replayed six original saved objectives per case with zero optimizer calls and
no reference or held data. Training window identities and the regional prior
were matched exactly. Posterior coverage is the fraction of the original full
winner's band-specific satellite mass whose identities exist in the independent
bank; it is not satellite identity truth. MAP agreement includes only windows
where both compared states assign at least 0.5 posterior mass to their top ID.

| Case/model/band | Full posterior mass covered | Confident MAP agreement | Closest independent seed to full winner (km) | Within any 25km fit domain? |
|---|---:|---:|---:|---|
| 001 C lower | 92.40% | 70.50% | 4.22 | yes |
| 001 C upper | 83.69% | 54.49% | 15.44 | yes |
| 019 C lower | 88.69% | 58.34% | 48.50 | no |
| 019 C upper | 12.84% | 5.10% | 223.70 | no |
| 019 B lower | 85.64% | 57.65% | 20.40 | yes |
| 019 B upper | 21.61% | 13.36% | 178.89 | no |

All selected C receiver integers remain receiver0=-1, receiver1=+2 in these
full and independent states. On 019, the upper independent pipeline changes
both available satellite support and reachable geography drastically. Its
different result cannot isolate the effect of adding channels to a fixed model.
The close original shared-half agreement depended materially on the shared
discovery/initialization recipe. This does not establish which basin is correct.

On 001, the full winner is geographically reachable in both independent
controls, and candidate coverage remains relatively high. The parent's separate
matched full-model checkpoint experiment is stronger causal evidence: after
the extra explicitly budgeted profile step, the lower/high anchored releases
were stationary and nearer the configured station (9.481/3.405km versus
21.266km), but the original full state retained the best objective and NLL.
NLLs were 41529.963, 41779.457, 43404.249 respectively; the nearer alternatives
had lower prior penalties (253.139/214.626 versus333.588). Exact band likelihood
decomposition also preferred the original state in each band separately.
Consequently missing starts, convergence, or positive band weighting of these
fixed likelihood states cannot alone explain/reverse this ranking.

The next diagnostic uses the existing orbit-blind bootstrap track memberships
to assess posterior identity switches, edge gaps, and confidence at these same
saved states. Cross-state identity differences above do **not** prove temporal
switching or justify adding a consistency penalty. Tracks themselves must be
audited before treating their membership as persistent satellite identity.

## Temporal identity audit completed

`local/ds22-track-identity-audit-v1` now contains the bounded zero-fit audit:
four saved-state evaluations for 001 and one for 019. No model was changed.
The threshold 0.5 and retention of all consecutive track edges were fixed
before execution. Track membership came from the existing orbit-blind
bootstrap reconstruction, without satellite posteriors or station reference.

| Case/state | Confident consecutive edges | MAP identity switches | Switch fraction |
|---|---:|---:|---:|
| 001 original / all-anchor release | 679 | 62 | 9.13% |
| 001 low-anchor release | 638 | 55 | 8.62% |
| 001 high-anchor release | 583 | 65 | 11.15% |
| 019 original | 654 | 70 | 10.70% |

The 001 graph contains 24 tracks, 979 of 3229 windows, and 955 edges.
Gaps have median 0.356s and maximum 3.904s. The 019 graph contains 24 tracks,
1026 of 3144 windows, and 1002 edges. Neither graph has overlapping track
membership or cross-channel edges; tracks are single receiver and channel.

Identity switching is present, but this diagnostic does not explain the
configured-distance ranking: the nearest 001 high-anchor state switches more
often, not less. Different confident-edge counts also limit comparison of raw
switch counts. Only roughly one third of windows occur in selected bootstrap
tracks, and physical track purity remains unverified. A naive consistency
penalty therefore has weaker support than a controlled test of the known B/C
temporal-calibration difference. No penalty or threshold was tuned using these
distances, and no further fit was launched by this audit.

## Original full-channel expansion: 035/037 runtime qualification

Both cases completed their original 100-point discovery and fitted-shape
stages. DS22-035 then completed all nine shape-bootstrap scientific calls and
assembled its candidate union and physical seed artifacts, but exhausted the
original 90-second stage cap during final recursive source/parent validation.
The failure is retained at `local/ds22-initialization-v1/DS22-035/shape-bootstrap`;
there is no fabricated original terminal and no repeated scientific call.

An explicit metadata-only recovery receipt under
`local/ds22-bootstrap-recovery-v1/DS22-035` validated all nine paired calls,
aggregates, candidate union, and seed layouts, then pinned the original bytes.
It completed in 20.233 seconds with zero optimizer, objective, or predictor
calls. This is a new qualified authority, not a reclassification of the failed
original slice.

The separate `ds22_initialization_authority` port qualifies genuine original
or explicitly recovered parents once and reconstructs the original discovery
bank separately from the later candidate union. Runtime reads check exact
ancestor/source/input/membership/TLE bytes; training preparation is replayed
through the original public provider and canonical receipt comparison.

| Case/qualified parent | Authority read | Preparation | Final authority check |
|---|---:|---:|---:|
| 035 recovered shape-bootstrap | 0.207s | 35.781s | 0.382s |
| 037 original shape | 0.382s | 34.385s | 0.219s |

Both zero-fit qualifications passed. A separate runtime stage consumer keeps
the original numerical operations, selectors, scientific budgets, and artifact
validation, with exclusive slice/call claims and no failed/orphan retry. Its
distinct schema makes the recovery lineage explicit. The first prescribed
stages are 035 hybrid and 037 shape-bootstrap, each slice 0 under its unchanged
240s/90s cap. Both completed, followed by the remaining stages below. The
original consumer is not monkeypatched.

| Case | Stage | Completed calls | Whole stage elapsed |
|---|---|---:|---:|
| 035 | Hybrid | 9 | 32.757s |
| 035 | Cold bootstrap | 9 | 26.704s |
| 035 | Six-proposal export | 0 | 20.683s |
| 037 | Shape bootstrap | 9 | 21.034s |
| 037 | Hybrid | 9 | 48.587s |
| 037 | Cold bootstrap | 9 | 15.826s |
| 037 | Six-proposal export | 0 | 15.432s |

Every row completed in its first numbered runtime slice, under the original
stage cap. The 035 recovered scientific calls were not repeated. Runtime
six-proposal terminal protocols are
`21414dd472f645b7ac16b9fc6da2758ce9f47cd90294bb992687e8e6dbba1818`
(035) and `75d591099d230df28cadcaadbb063e2b9fc9951825efae53f304f13019e363fc`
(037).

The explicit full-model adapter `tools/ds22_runtime_models.py` now consumes
these genuine runtime authorities. It retains original A/B/C model creation,
training frame metadata, six physical starts, six receiver-lift derivations,
sequential A stages, stationary acceptance, and 20s/600-iteration fit caps.
Unit budgets remain 90s for A and 165s for B/C; failed/orphan attempts cannot
resume. Original receipt validators check the resulting units. Component
verification exercised real synthetic public training/model construction,
all 54 prescribed model calls, all 12 terminal validators, final sealing,
and cached re-entry without refitting. Tests passed; frozen scientific modules
were unchanged.

Actual full-model preparation qualification completed with zero optimizer,
objective, or predictor calls:

| Case | Initial authority | Training preparation | Final authority | Total |
|---|---:|---:|---:|---:|
| 035 | 0.372s | 17.842s | 0.352s | 18.567s |
| 037 | 0.385s | 13.658s | 0.367s | 14.410s |

Both physical initializations passed. The first A path in each case completed
all three stages stationarily. The remaining 22 units are queued/running in
two bounded worker chains; each chain stops at a failure or checkpoint instead
of silently continuing that attempt. No position comparison for these cases
has been performed at this update. The new reporting adapter reads the explicit
configured reference only after the entire matrix seal and retains the
unconfirmed-station and shared-half limitations.

Implementation commits: metadata recovery `08940c0b7`; qualified authority
`b88097641`; stage runtime `6adcc5806`; full-model composition `6696cc031`;
post-seal reporting `bcbd132e9`. Runtime artifacts are under
`local/ds22-{bootstrap-recovery,initialization-authority,initialization-runtime,runtime-models}-v1`.

## Nine sealed DS22 development matrices

Both new matrices have now sealed all 12 units. DS22-035 used 52 actual fits,
50 stationary; DS22-037 used 54 fits, all stationary. The two rejected 035
fits were A-start5/lower and B-lower/start5, with identical scaled KKT residual
0.002051 despite solver success after about 1.09 seconds. This was not a
deadline failure. The sequential A path correctly skipped upper/final stages
after its rejected lower fit; nothing was retried.

The first nine available development matrices are shown below. These are
distances in kilometres to the **configured, unconfirmed** station, not verified
accuracy; locked evaluation cases have not been used. Lower/upper columns in
this table share discovery and initialization. The separate independent controls
above are different experiments and must not be substituted silently.

| DS22 | A all | B all | B lower | B upper | C all | C lower | C upper |
|---|---:|---:|---:|---:|---:|---:|---:|
| 001 | 3.750 | 0.785 | 3.555 | 6.440 | 21.266 | 23.645 | 12.163 |
| 003 | 1.903 | 1.819 | 2.809 | 2.829 | 2.828 | 4.132 | 1.643 |
| 017 | 1.532 | 3.059 | 2.463 | 1.638 | 3.769 | 3.303 | 2.042 |
| 019 | 107.371 | 113.239 | 166.428 | 154.377 | 142.114 | 203.397 | 214.751 |
| 029 | 3.296 | 0.841 | 4.087 | 2.133 | 2.392 | 5.988 | 0.796 |
| 031 | 0.168 | 0.510 | 1.027 | 3.018 | 1.169 | 2.257 | 5.790 |
| 033 | 1.793 | 1.478 | 0.412 | 1.927 | 1.975 | 1.090 | 3.424 |
| 035 | 0.597 | 0.289 | 0.695 | 0.878 | 0.507 | 0.315 | 1.203 |
| 037 | 1.802 | 3.967 | 4.429 | 17.266 | 6.425 | 4.688 | 16.781 |

| Statistic over these nine cases | A all | B all | C all |
|---|---:|---:|---:|
| Median configured distance (km) | 1.802 | 1.478 | 2.828 |
| Configured distance below 1km | 2/9 | 4/9 | 1/9 |
| Configured distance below 0.5km | 1/9 | 1/9 | 0/9 |
| All no worse than both shared halves | not a standalone A comparison | 7/9 | 2/9 |
| All worse than both shared halves | not a standalone A comparison | 1/9 | 1/9 |

C all is farther from the configured station than B all on all nine cases.
Adding 035/037 expands coverage; it is not an algorithm improvement on matched
old cases. The nine-case subset does not establish performance on all 44 ready
development cases or the locked evaluation set, and the sub-kilometre/0.5km
median goals remain unmet even conditionally on this reference.

The new comparisons are sealed at
`local/ds22-runtime-configured-comparison-v1/DS22-{035,037}`. They were computed
only after both new matrices had sealed; original-case comparisons remain at
`local/ds22-configured-comparison-v1`. Training-only minimum-stationary-objective
selectors were fixed before comparison. No model, start, or half was selected
using the reporting distances.

## Training-only local curvature: completed, no new fits

The original C and selected native-clock states on 001/019 were replayed with
all physical and nuisance parameters included. The protocol fixed two central
finite-difference steps in optimizer-scaled coordinates (1e-4 and 5e-5), at most
600 objective/gradient evaluations and 180 seconds per case. It prohibited
reference and held-data access, optimizer calls, and silent regularization.
The nuisance Schur complement was computed only for a positive, nonsingular
nuisance Hessian at the prescribed relative eigenvalue tolerance 1e-10.
Hessian relative step/asymmetry tolerance was 1e-3; profile eigenvalues also
had to agree in sign and within 10% between steps.

Both cases completed: 001 used 514 evaluations in 57.025s; 019 used 434 in
45.188s. All four state Hessians and computed profile spectra passed these
stability checks. The entries below use the smaller finite-difference step.
The geography block eliminates **all** remaining physical/timing/calibration
and clock/group parameters, not just newly added clocks.

| Case/state | Active original constraints | Geography-profile eigenvalues (objective units/km²) |
|---|---|---:|
| 001 original C | Upper satellite timing bound, satellite 63720 | Unconstrained extension: −1.868, 15.947 |
| 001 selected native-clock C | none | 7.782, 14.006 |
| 019 original C | none | 17.628, 47.719 |
| 019 selected native-clock C | none | 10.779, 35.914 |

The negative unconstrained 001 eigenvalue does **not** invalidate its accepted
constrained fit. The weak direction changes the active timing constraint; the
Hessian restricted to its equality tangent is positive (minimum eigenvalue
9.227), with tangent-normal residual below 2e-16. The selected state is 23.433km
from its 25km search-disk centre, so this active constraint is satellite timing,
not the geographic search disk. The diagnostic does not substitute an
unconstrained step or relax that timing bound.

Both 019 states are interior local basins with positive observed Hessians.
Their geographic profile curvatures remain positive, with no near-null
geographic direction under the fixed tolerance. The weakest full native-clock
mode has eigenvalue 0.202 and 99.84% of its squared norm in optimizer-scaled
clock coefficients; geography contributes approximately 0.0028%. Thus these
selected states do not support a simple local geographic collapse explanation.
The clock-profile curvature comparison is between different fitted states and
is descriptive, not a causal estimate of information lost by adding clocks.

These are local **penalized observed-objective** curvatures. They are not Fisher
information, position uncertainties, proof of global identifiability, or proof
of correct satellite identities. Equality-tangent diagnostics do not replace
a full inward-cone/Lagrangian second-order analysis. Combined with the earlier
019 candidate-support and search-domain divergence, the evidence points toward
global association/basin discrimination as a more useful next investigation
than additional small steps inside these already locally stiff basins.

Artifacts: `local/ds22-c-curvature-v1/DS22-{001,019}`; source/protocol commit
`699658280`. Component tests cover two-step quadratic Hessian/Schur closure,
indefinite/singular nuisance refusal, and actual original-bound tangent
construction. No scientific model or selection was changed by this audit.
