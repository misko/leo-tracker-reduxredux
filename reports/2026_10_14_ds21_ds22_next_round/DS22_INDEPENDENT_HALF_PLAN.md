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
