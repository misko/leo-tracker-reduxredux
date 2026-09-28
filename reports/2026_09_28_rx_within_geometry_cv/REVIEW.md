# Independent pre-fit review: within-sequence geometry cross-validation

## Decision

The proposed leave-one-recording-out experiment is a useful bounded diagnostic of whether
directional terms transfer through motion within a recording, rather than relying on average
geometry differences between recordings or lanes. It may proceed after the executable isolation
and centering gates below pass. It uses six calibration recordings whose broader outcomes have
already informed the research sequence, so it is post-outcome model diagnosis rather than new
confirmation.

This experiment cannot establish satellite identity, physical target presence or a calibrated
antenna pattern. The T arm still encodes the nominal, provisionally mapped east/west fixture pose.
Without geometry controls in this stage, a positive within-T contrast would justify further
testing, not a physical tilt claim.

## Fold boundary

Create exactly six folds, holding out one entire calibration recording in each. Within every fold:

- fit the already selected `joint` observational reference anew on the other five recordings'
  reception windows; do not rerun mode selection;
- refit the geometry scaler exactly as in the original model using all training-reception
  nominee-by-receiver feature rows, excluding `other` and without nomination-prior weighting;
- fit every D/E/S/T arm using only those five records' reception observations;
- score every reception window in the held recording sequentially from the frozen conditional
  nomination prior, before updating on that window;
- start a separate filter for every exact lane and use actual timestamp gaps.

The fixed 500 Hz signal width is historical carry-forward, not selected by this cross-validation.
Candidate nominations and their conditional priors are also frozen inputs. State that a held
record's nomination prior may use its earlier designated training observations; it must not use
the reception outcomes scored here.

No original held-frequency window, original four-record pilot evaluation outcome, or later
confirmation record may be read by extraction, fitting, scoring or diagnostics. Require the six
held fold IDs to partition the 1,356 calibration-reception source window IDs exactly once.

## Absolute and within families

The absolute family uses the fold-standardized frozen features directly. For the within family,
first standardize with the five-record training scaler, then subtract the reception-window mean
of columns 3 through 7 separately for every lane, nominee and receiver. Include all forecast rows
in this mean, regardless of predicted visibility; visibility is an emission property and must not
silently change the covariate definition. Leave columns 0 through 2—intercept, receiver contrast
and sample-rate term—unchanged.

Apply the same rule to the held recording using its complete, known reception forecast schedule.
This is transductive covariate conditioning: future forecast covariates within the held reception
sequence are available, while future candidate-set outcomes are sealed. It is valid for the
declared “forecasts available at sequence start” estimand, but it is not an online-causal feature
transformation. Report that distinction explicitly.

Because centering changes only columns 3 through 7, absolute D and within D must be exactly
identical in every fold: same arrays, starts, fitted parameters, state nuisance and held score.
Treat any difference as an implementation failure. Verify centered geometry means are numerically
zero for every training and held lane/nominee/receiver group while the first three columns remain
bit-identical.

E remains D plus centered up, S adds centered north/east, and T adds centered signed-east tilt and
its up interaction. Center the already constructed interaction column rather than reconstructing
an interaction from separately centered inputs; those are different models.

## Optimization and scoring

Reuse the joint MAP priors, bounds, exact-null competition and two-start L-BFGS-B procedure. D's
second start must be the declared neutral `[-2,0,0]` beta with neutral state nuisance, never the
all-calibration fit. For E/S/T, a nested start may inherit only the selected preceding arm from the
same fold and same feature family. Do not transfer parameters across folds or between absolute and
within families.

Save both optimizer receipts, likelihood and penalty components, selected/null state, active
bounds and fold membership. If neither start converges, fail the complete run. Do not remove a
fold, widen a bound, increase iterations, or choose a different start after seeing held scores.

Held full density equals the fold-specific joint reference density plus relative signal evidence.
Report the reference and D/E/S/T full and relative scores per record and denominator. Aggregate by
equal-record mean over the six folds, with paired record differences and sign counts. The primary
within-family contrasts are T-minus-D and T-minus-S. Also report E-minus-D and S-minus-E, and the
same contrasts in the absolute family. Compare raw and within versions by paired record, not by
pooling windows.

## Required executable gates

1. Perturb every held recording's counts and frequencies and require its fold's background,
   scaler, centers and fitted parameters to remain unchanged. Perturb original held-frequency and
   evaluation data and require the entire result to remain unchanged.
2. Verify every fitted background has exactly the five training recording IDs and normalized
   infinite count support; every scaler has the same five-record provenance.
3. Assert exact source-window uniqueness, six disjoint folds, 1,356 total scored windows and
   identical denominators across families and arms.
4. Test within means, unchanged nuisance columns, interaction-centering order, invisible forecast
   inclusion and candidate-permutation invariance.
5. Require exact absolute-D/within-D identity at feature, fit and score levels.
6. Test D's two prescribed starts, same-fold/same-family nested inheritance, preceding-null
   behavior, deterministic best-start selection and both-start failure.
7. Recompute every fold score, paired contrast, equal-record mean and sign count independently.
8. Benchmark a representative full-dimensional fold/family fit. Preserve the 300-second,
   one-thread, 4 GiB hard bound and fail without partial scientific output if it is exceeded.

## Interpretation

A within-family gain would show that centered forecast motion predicts candidate-set reception
within these six reused records under the frozen nominations and empirical reference. It would
reduce concern that an absolute result is driven only by global receiver or lane differences.
It would not prove the nominal physical pose, because within east motion can correlate with time,
elevation, visibility, catalogue choice and other unmodeled sequence effects.

A weak or unstable within result has two possible meanings: the directional response is
misspecified, or these sequences do not contain enough independent within-record directional
variation after nomination uncertainty and centering. Interpret it alongside the frozen support,
pose-provenance and catalogue-grouped nomination audits. Do not tune a new geometry form on these
six fold scores or combine them with the eight reused held records as independent confirmation.

## Executable pre-launch review

The reviewed runner correctly constructs a reception-only document before reading observations,
refits the selected joint reference and original scaler inside each five-record training fold,
centers the already standardized columns 3 through 7 over each lane/nominee/receiver time axis,
and leaves columns 0 through 2 unchanged. It uses all forecast rows regardless of visibility.
Held reception sequences are scored prequentially with the scalar-equivalent joint calibration
recursion, and D receives two identical neutral starts rather than an all-calibration warm start.
Ruff passes on the runner and its tests.

Two integrity blockers remain before the first run:

1. Enforce the hard D identity in the runner. It currently computes absolute and within D twice
   but does not compare their fitted receipts or held scores. Require the selected beta/state,
   candidate objectives, reference/relative/full scores and denominators to agree exactly or at a
   declared numerical tolerance no larger than `1e-12`. Add a run-level regression that fails
   when the within transform changes a D column.
2. Bind checkpoints to the complete frozen experiment, not only the dataset digest. The current
   loader will accept a fold produced by changed runner, dependency or protocol bytes whenever the
   dataset is unchanged. Store and verify an experiment seal derived from the launch-frozen source
   and configuration hashes. Also require the checkpoint's held session to equal the session
   assigned to its filename/index and its training-session set to equal the other five records.
   This must be fixed before launch because bounded timeout continuation is part of the declared
   execution path.

Add `positive_records` to every aggregate so the promised signed-pair summary is explicit rather
than left for a later report to infer. No other fold-isolation, centering, likelihood or scoring
defect was found. The five focused synthetic tests pass according to the implementation handoff;
the real-data fit remains sealed pending these fixes and the final installed-API receipt.

The final frozen source closes these gates. Each fold now requires exact equality of the complete
absolute/within D fit receipts and held-score dictionaries; the live execution has passed this
assertion through its completed folds. Every aggregate includes a positive-record count.
Checkpoints carry a schema, dataset digest, held and training membership, fixed settings, source
fingerprints and the experiment seal derived from the complete launch hash map. The loader rejects
any mismatch, and checkpoint creation remains exclusive after both families complete.

The installed suite passes eight tests in 0.87 seconds and Ruff passes. A continuation must still
recompute every hash in the original `launch.json` before invoking the runner with its original
seal; the seal is a binding value, not permission to skip external byte verification. With that
continuation rule, the source and checkpoint protocol are sound. No frozen source was modified by
this final review.

## Independent post-run outcome review

The complete six-fold run exited successfully in 259.00 seconds with 132,288 KiB maximum resident
memory, inside the frozen limits. Every launch source/input hash matches the reviewed bytes, the
experiment seal recomputes from that hash map, the result embeds the same dataset digest, and all
six checkpoints carry the matching seal and correct fold membership. Their 1,356 held source
window IDs are unique and cover the full calibration-reception population exactly once.

All optimizer starts converged. The hard absolute/within D invariant holds exactly for every fit
receipt and held score. Every one of the 48 selected arm/family/fold fits places tau at the
10-second upper bound, so persistence remains unresolved and boundary-censored. Aggregate means
and positive-record counts independently recompute.

| contrast | nats/window | positive records |
|---|---:|---:|
| within T minus within D | +0.194879 | 5/6 |
| within T minus within S | +0.107732 | 5/6 |
| absolute T minus absolute D | +0.213174 | 5/6 |
| within T minus absolute T | -0.018295 | 3/6 |
| within E minus absolute E | +0.049098 | 4/6 |
| within S minus absolute S | +0.050542 | 4/6 |

Within T transfers better than within D and S on five of six omitted recordings. Absolute T also
transfers better than D on five of six and has a slightly larger mean gain. Centering therefore
does **not** improve T overall; its paired within-minus-absolute contrast is negative and splits
3/6 by sign. The result shows that within-sequence directional variation carries predictive
information under this reused calibration design, while providing no evidence that removing
between-sequence levels improves the full T model.

The fold-specific D model beats its joint reference by `+3.738066` nats per calibration-reception
window, positive in all six records. This is far larger than the earlier all-calibration D gain of
about `+0.0548` on eight evaluation held-frequency records. Those numbers use different record
populations, forecast horizons, fold-specific references/scalers and temporal roles. Their gap
cannot be assigned to any one cause and must not be presented as a comparable treatment effect.

The provisional pose remains decisive for interpretation. T's nominal signed east/west terms are
not a surveyed physical 20-degree response, this experiment includes no swap/reversal/shift
controls, and all tau estimates are on a boundary. The result is useful directional-transfer
diagnosis, not model selection, satellite identity, physical tilt validation or promotion.

## Next temporal-transfer diagnostic

The clean next step is a separate frozen, no-refit diagnostic: apply each existing five-record
fold model, scaler and joint reference to that fold's omitted calibration recording through its
previously sealed held-frequency segment. Filter the omitted reception segment first, carry its
posterior across the real time boundary, and score every held-frequency window before updating.
Report reception and held-frequency gains with their original denominators for the same fold and
model; do not refit coefficients, reference, scaler, sigma, occupancy or tau.

This paired temporal-role comparison can show whether predictive gains decay between near-prefix
reception forecasts and later held-frequency forecasts within the same omitted records. It still
cannot uniquely separate forecast age, role construction, target intermittency and population
change, and the held-frequency outcomes require a new protocol and frozen receipt before access.
Do not retrofit those scores into the completed cross-validation selection or use them to tune a
new persistence bound.
