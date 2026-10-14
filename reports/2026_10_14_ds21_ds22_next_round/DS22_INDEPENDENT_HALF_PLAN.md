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
