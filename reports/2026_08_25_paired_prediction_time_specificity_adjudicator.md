# Paired prediction-time specificity adjudicator

Date: 2026-08-25

Status: the atomic explicit-shortlist prototype is implemented in
`tools/replay_raw_multipath_paired_prediction_time_specificity.py`, with owned
tests in
`tests/analysis/test_raw_multipath_paired_prediction_time_specificity_tool.py`.
It uses the general non-affine block-permutation core and leaves the existing
correct-time replay and block-control contracts unchanged.  No real dwell was
run as part of implementation.  The current independent correct-time and
block-control receipts still do not acquire common producer provenance
retroactively and remain unadjudicated.

## Question answered

The proposed adjudicator asks a deliberately narrow question:

> On one fixed raw RF inventory, objective, finite catalogue/nuisance search,
> and window, does the identity prediction-time arm fit better than every
> frozen prediction-time control arm?

It is a conditional prediction-time test.  It is not a signal-absence
control, a raw false-positive-rate estimate, a proof of catalogue identity,
or evidence that a payload was decoded.

## Audit of the matched 115401 artifacts

The matched correct-time receipt is
`replay-correct-time-matched-10s-minus2-to-plus2-step0p1.json`, with file
SHA-256 `09aa95e776c1f8401bad1892e6e4e63674725c5da0a4e0fb989dc4173719bfc0`.
The frozen control receipt is `control-0.json`, with file SHA-256
`9ba6e23b90707be5aa97c58a768922cd2bed3df588773469aa8b7c3c834825b5`.
Both embedded search-configuration digests recompute, and all six referenced
duration-input, calibration, and TLE files in each receipt still match their
declared byte digests.

The receipts agree on:

- session and recording-manifest digests;
- the ordered four path IDs and duration-input byte digests;
- pilot-scan content digests (the correct-time receipt binds them in its
  embedded search configuration);
- the exact 10.0-second, 100-cell UTC window and probe epoch;
- the score-calibration and TLE byte digests;
- observer geometry (the non-semantic label differs);
- every multipath cost and nuisance configuration value;
- the final catalogue identities `[58937, 62227, 67617]`;
- a null objective of `10274.815304030146`; and
- a 64-of-64 retained final Cartesian evaluation with four retained states
  from 656 generated states for each final catalogue identity.

On those matched fields, the descriptive score is:

```
correct-time delta       = -4182.442026797205
strongest control delta  = -2388.9100105385114
correct-time advantage   =  1793.5320162586931
```

This is useful descriptive evidence that the correct prediction epochs fit
better in this run.  It is not a paired-gate pass.  The correct-time producer
accepted an explicit three-object shortlist and did no catalogue search.  The
control producer screened 449 full-window-visible catalogue objects, refined
32, and selected its final three with a data-dependent coarse-to-fine
heuristic.  The producer algorithms and search-selection histories are
therefore different.  Both final per-catalogue state banks are also pruned.
The control selected all three objects and improved on the null by 2388.91,
which is a direct deranged activation witness even though it did not beat the
correct-time objective.

## Smallest safe architecture

Add one new Research-only paired runner and leave the existing v2 replay and
v1 control receipts unchanged.  The runner should load and validate the raw
paths once, construct the common decision problem once, freeze the complete
arm family before any arm is scored, and emit one atomic receipt containing
the identity arm and every control arm.  Only the prediction-epoch transform
may vary between arms.

The first lean mode should use one digest-bound, predeclared catalogue
shortlist in every arm.  It is explicitly conditional on that shortlist.  A
later full-catalogue mode may be added only when the same finite catalogue and
nuisance universe can be searched, or rigorously bounded, in every arm.
Independently selecting a shortlist in each arm is not an identical search
universe.

The runner needs a frozen family plan.  At minimum the plan binds:

- a family label and the exact ordered arm IDs;
- one identity arm and one or more unique control labels;
- session, recording manifest, ordered path, duration-input, and pilot-scan
  digests;
- absolute UTC window, cell grid, probe epoch, and exact selected probe set;
- calibration bytes/content, candidate-cap scope, all score/structural costs,
  and objective version;
- TLE bytes, observer, horizon rule, RF eligibility, and exact catalogue IDs;
- delay grid, CFO-mode proposal algorithm/configuration, state retention and
  search caps, solver/tie versions, implementation digests, and runtimes;
- every control mapping or the deterministic label/context inputs that
  uniquely produce it;
- a nonnegative minimum-advantage threshold and strict comparison semantics;
  and
- whether independent preregistration or timestamp causality was actually
  verified.  A digest alone binds bytes but does not prove when they were
  chosen.

The atomic output should expose the following canonical digests separately,
not hide them in a single opaque search digest:

1. `raw_problem_digest`: all probes, UTC estimates, cell assignments,
   usability, raw candidate bundles, modeled observations, exclusion groups,
   score costs, elided constants, and cap accounting for every path.
2. `objective_digest`: detector and structural costs plus exact objective and
   null-construction semantics.
3. `search_universe_digest`: exact catalogue identities, path/RF eligibility,
   delay/CFO state rules, finite caps, solver, and deterministic tie order.
4. `producer_digest`: all result-changing source and numerical runtime
   versions common to the arms.
5. `family_plan_digest`: the complete frozen arm set, transforms, and gate
   policy.

Each arm then adds only its transform kind/digest, mapping receipt, evaluated
state accounting, exactness/bounds, selected identities, and objective.  The
identity transform must map every probe epoch to itself.  A block control must
be a bijection shared across paths/catalogues, preserve within-block offsets,
break forward adjacency, and have realized minimum displacement strictly
beyond the entire allowed delay support.

Permutation plans need not leave prediction epochs in observation order.
Each path/catalogue/delay propagation therefore sorts the unique mapped UTC
epochs, calls the propagation boundary on that strictly increasing sequence,
and inverse-maps Doppler, elevation, and altitude back to observation-probe
order before proposing CFO modes or constructing fixed hypotheses.

## Required comparability invariants

The adjudicator fails closed as `not_comparable` unless all of these hold:

1. The family-plan and common component digests recompute from the emitted
   content, and every referenced input file still matches its byte digest.
2. Exactly one declared identity arm and every declared control arm are
   present; there are no extra arms, duplicate IDs, duplicate mappings, or
   omitted inspected controls.
3. Every arm refers to the same raw-problem, objective, search-universe,
   producer, TLE, observer, RF-eligibility, window, and family-plan digests.
4. The only arm-varying prediction input is the declared epoch transform.
   Raw observations, candidate caps, CFO proposal policy, costs, catalogue
   identities, nuisance grids, pruning/caps, and solver/tie order are equal.
5. The null cost and elided constant are bit-identical across arms.  Each
   finite arm objective satisfies `delta = total - null` within one declared
   serialization tolerance; that tolerance is an integrity check, never a
   data-selected decision margin.
6. The identity mapping and every control mapping validate structurally, and
   the submitted mapping set equals the frozen family plan.
7. Search exactness or rigorous objective bounds have the same meaning in all
   arms.  A control null may be certified despite retained-bank pruning only
   by the additive/exclusive-group separability proof: the path-offset
   Cartesian is exhausted and every generated exact single fixed state is
   nonselected with nonnegative delta.  A merely unevaluated prefix cannot
   support a positive gate.
8. Any saturated upstream candidate cap and lack of pre-acquisition/physical
   inventory completeness are propagated, never upgraded by the adjudicator.

## Score and gate semantics

For arm `a`, let `Delta_a = C_a - C_null` and define the nonnegative observed
improvement `I_a = max(0, -Delta_a)`.  For controls `j`:

```
strongest_control_improvement = max_j I_j
paired_advantage = I_identity - strongest_control_improvement
                 = min_j Delta_j - Delta_identity  (when all arms activate)
```

The maximum, not the mean or a selected control, is the familywise comparison.
A tie counts against the identity arm.  The raw cost advantage is primary
because the evidence window is identical; per-cell and per-usable-probe
values may be emitted only as descriptive normalizations.

The output should separate a descriptive score from a conservative gate:

- `not_comparable`: any invariant fails; do not emit a paired conclusion.
  This is the paired disposition of the two current 115401 receipts.
- `identity_nonactivation`: the identity arm does not beat the null.
- `deranged_activation_witness`: at least one frozen control beats the null.
  Report the paired advantage, but do not pass the conservative zero-control
  gate.  The current 115401 control independently has this result, although
  its mismatched correct-time receipt prevents paired adjudication.
- `control_null_not_certified`: no evaluated control activated, but at least
  one control lacks the separability certificate over its declared finite
  state universe.
- `advantage_below_frozen_threshold`: exact/bounded arms are comparable, but
  the identity advantage is not strictly greater than the plan threshold.
- `bounded_prediction_time_gate_pass`: the identity has an exact or
  lower-bound activation witness, all declared controls are separability-
  certified nulls over their finite state universes (or satisfy a separately
  calibrated, frozen control policy), the witnessed strict advantage threshold
  is met, all arms are accounted for, and selection causality requirements in
  the plan are met.

Even the last state must retain `candidate_only=true`,
`specificity_claimed=false`, and `payload_decoded=false`.  It supports only a
bounded conditional prediction-time statement.  Spacecraft identity also
requires a predeclared target or a calibrated actual-time catalogue-separation
gate, while tracking additionally requires coherent support across independent
times/dwells.

A looser `relative_advantage_pass` may be reported descriptively when controls
activate but the identity arm wins by the frozen margin.  It must never be
silently relabeled as the conservative gate or as spacecraft specificity.

## Multiplicity and inference limits

- Multiple permutations of one captured session are dependent controls, not
  independent trials.  They contribute one session replicate.
- All generated or inspected labels must be included.  Retrying labels and
  retaining a favorable subset invalidates the family.
- The strongest submitted control provides a familywise rejection rule, but
  neither its rank nor the count of nonactivating controls estimates a raw
  false-positive rate.
- Neither the legacy constrained affine derangement nor the bounded general
  non-affine control generator is established as exchangeable with the
  identity mapping.  Therefore `(1 + exceedances) / (m + 1)` is not a valid
  permutation p-value here.
- Dwell selection, candidate selection, observer selection, window selection,
  and structural-cost tuning are additional multiplicities.  A positive
  threshold must be calibrated on disjoint sessions and then frozen for a
  holdout cohort.
- Independent capture sessions, not paths, episodes, satellites selected in
  one fit, or mappings of one session, are the appropriate replication unit.

## Tests required before implementation is trusted

### Contract and provenance tests

- Recompute every common and family digest; reject one-byte changes to each
  bound component and each referenced file.
- Reject missing, extra, duplicate, or reordered-when-order-is-semantic arms;
  verify order-independent control aggregation where order is not semantic.
- Perturb, one at a time, raw inventory, UTC window, calibration, cost,
  candidate cap, TLE, observer, catalogue identities, RF eligibility, delay
  grid, CFO proposal policy, search cap, solver, tie order, runtime, and
  implementation digest; every case must become `not_comparable`.
- Reject a nonidentity reference map, nonbijective control, mapping reused
  under two labels, path/catalogue-specific mappings, preserved forward
  adjacency, or displacement that overlaps allowed delay support.
- Reject NaN/infinity, objective/null inconsistency, and a family plan whose
  digest or declared arm set does not recompute.

### Numerical and decision tests

- Verify `paired_advantage` against hand-computed one- and multi-control
  examples; the strongest control and deterministic tie key must be stable.
- Treat exact ties and threshold equality as failures under the strict `>`
  rule.
- Cover identity nonactivation, a weaker activating control, a control that
  ties/beats identity, fully retained control nulls, pruned-but-certified
  control nulls, and incomplete path-offset control nulls.
- Prove that an activation witness remains a valid negative diagnostic under
  retained-bank pruning, that a pruned identity activation is a lower-bound
  improvement witness, and that an incomplete nonactivation cannot create a
  positive gate.
- Verify that candidate-cap saturation and unverified preregistration remain
  visible in every outcome, including a bounded gate pass.
- Verify that no outcome sets `specificity_claimed` or `payload_decoded` true.

### Unified-runner integration tests

- Build one synthetic raw problem once and show byte-identical common digests
  in identity and control arms, with only prediction epochs changing.
- Run identity plus two frozen controls atomically; prove every planned arm is
  present even when the first control already rejects.
- Exercise the same exact catalogue/nuisance set in all arms and reject any
  arm-local shortlist selection.
- Assert that every propagation call receives strictly increasing mapped
  epochs and that its Doppler/elevation/altitude arrays are restored to
  observation-probe order before scoring.
- Round-trip the new receipt through canonical JSON and reproduce its content
  digest.
- Include the two current matched 115401 receipts as a negative fixture: they
  must be classified `not_comparable` because their producer/search-selection
  histories differ, while their 1793.532 descriptive cost advantage may be
  reported explicitly as unadjudicated.

## Implementation threshold

The atomic paired producer and pure fail-closed reducer now exist.  The v1 CLI
cannot self-assert calibrated thresholds or external preregistration; those
flags remain false.  Its bounded positive-gate state is therefore specified
and unit-tested but cannot be emitted by an ordinary CLI run without a future
independently verified plan/threshold authority.  The scientifically truthful
disposition for the already completed independent 115401 artifacts remains:
correct time fits substantially better, but a strong deranged activation
remains and paired prediction-time specificity is not established.
