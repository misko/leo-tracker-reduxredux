# DSX01 recovery: iteration 5 checkpoint

Goal status: **active**. The preceding goal turn was progress: it completed the
215-pair element-age audit, actual orbital displacement propagation, component
tests and saved plots. This turn adds independent historical consistency
evidence, a working heterogeneous timing-prior model, genuine training-only
blocked prediction, failure decomposition, a metadata-only candidate inventory
and conditional permutation controls. This is not a no-progress or blocked turn.

## Current evidence

- [Complete-protocol plots and all-window comparison](comparison/README.md):
  best descriptive development count 462/693 and eight strongly restored
  windows, versus original 96/693. That constant-Hz satellite residual model
  fails excluded-half conditional likelihood in 39/40 fits. No promotion.
- [Cold forecast diagnosis](cold_prediction_diagnosis/README.md): original
  full-data winner IDs are absent from the first-half-discovered bank on
  1190/1410 original held assignments. Restricting the unchanged original
  classifier to overlapping IDs reduces held support from 1410 to 267; the
  actual cold predictor assigns 165/1982. These are posthoc diagnostic labels,
  not true identities. Remaining same-ID residuals and calibration extrapolation
  also deteriorate. Strong local Jacobian dependence is not posterior covariance.
- [Blocked cold interpolation](blocked_cold/README.md): whole-probe alternating
  20-second blocks, fixed parity0, S03 chosen before outcomes. Public original
  policy learns its bank, position and calibration from 2073 training winners
  only. Strict KKT0.000167863, runtime147.784s, 45 selected IDs. Training support
  1088/2073; held795/1909; boundary2/6. Requested held support66/80:
  window00720/26,00820/28,00926/26. Other sources'555 requested points remain
  untested in this pilot. No no-extrapolation/forecasting causal claim: the
  cohorts, learned banks and calibrations differ from the half assay.
- [Frozen-predictor conditional controls](predictor_null/README.md): 32
  within-RX/channel held CFO permutations. Blocked actual795/1909 versus
  nullmean201(range181–238), requested66/80 versus6.875(range3–12).
  Half actual165/1982 versus134.156(range117–156), requested2/84 versus
  4.281(range0–9). Actual assignments first replay exactly and training rows
  remain unchanged. This supports temporal alignment, not verified identities
  or a calibrated discovery false-positive rate. `null-rf-lane-check.json`
  confirms every one of the16 RX/channel lanes has exactlyone RF frequency,
  so these within-lane permutations do not break an RF covariate relationship.
- [Metadata-only candidate inventory](metadata_bank/README.md): public
  whole-prior/whole-capture eligibility retains845/11,149 STARLINK IDs in5.92s;
  covers all original40/cold25 IDs and1410 original held winner labels.
  No CFO scoring or fitting. Dense work would be33.8×the25-ID cold bank;
  do not create845 independent unconstrained timing/q parameters or call
  increased chance matches recovery.
- [Age audit](age_audit/README.md): original215 pairs aged5.07–44.25h;
  71 relative shifts>10s; correlation(age,absolute relative shift)−0.0068.
  Actual10s orbital motion72.60–77.64km. Fitted shifts are not physical error labels.
- `age_timing/`: independent historical same-provider consistency uses only
  snapshots collected before the earliest DSX source.18 snapshot pairs,
  36 propagation calls, zero localization fits for calibration. Space-Track
  12–24h robust core0.7755s,24–48h1.9452s; tails and perpendicular discrepancies
  are much larger. Young HF support is inadequate. The initial single-node
  API-contract failure is preserved; v2 uses three strictly causal instants and
  the same frozen snapshot/ID policy. Newer elements are not truth.

## Work in progress and next authorized comparisons

1. Age-prior pilot: freeze provider/age rule before fits; require100 distinct
   historical objects/bin, clip supported core widths to0.5–2s, otherwise use
   baseline2s. The fallback can be nonmonotonic; no unsupported extrapolation.
   Keep common3s unchanged. S01HF is an exact all2s zero-fit negative control.
   S03ST has14 widths0.775488,one1.945240,and25 baseline2. Exact scalar nesting,
   gradients, gauge-aware profile changes and excluded-CFO invariance pass.
   Eight warm S03 outcomes (2priors×2methods×2c arms) are sealed and evaluated.
   Fitted-c continuation assigns3467→3466/3988 and136→136/138 requested;
   configured distance3.282→3.221km. Both endpoints are strict. Fitted-c profile
   assigns3552→3550 and136→137 requested, distance3.098→3.158km; scalar control
   is numerically rejected (KKT0.002147), age endpoint strict. The c=0 results
   remain separate in `age_timing/pilot_evaluation.json`. There is no substantial
   fitted-c recovery or sub-km result, and no cross-prior J ranking is used.
2. Next: four matched training-only blocked
   continuations, scalar2 versus age policy × fitted-c/c=0, each1000 objectives
   and120s. Same public blocked seed/bank/calibration, no warm full-data seed.
   Freeze fits before held scoring; raw cross-prior J is not model evidence.
   c=0 is conditional after fitted-c production discovery, not a whole-pipeline
   c=0 run. Use verified `blocked_cold/training_context.py` ports; predictions
   use the unchanged base data model because only the prior changes.
3. Calibration-only band-contrast audit is complete in `band_contrast_audit/`:
   fixed blocked geometry/timing/q, training-only exact disjoint RX high-band
   profiles with the existing once-only absolute50000Hz contrast prior and
   predeclared identical grids/bounds/budgets. Fitted-c chooses RX1−25Hz and
   RX2+2925Hz, train1088→1108, held795→805 (+40new/30lost), heldNLL
   23241.168→23155.932. Requested held66/80 is unchanged. c=0 conditional seed
   chooses−425/+2225Hz, held405→500 andNLL25196.099→24801.587, requested54/80
   unchanged. Both selections freeze beforeheldscore;159evaluations/arm,
   ~0.10s profiles, four passingtests. This is no fulljointKKT or geographic claim.
4. Next joint-contrast investigation: preserve the original likelihood/q and
   once-only absolutecontrastprior but free the two band contrasts alongside
   existing parameters. Build/test exact nesting, all gradients and bounds
   before one matched4-case blocked continuation (fixed/free ×c/c=0), each
   1000objectives/120s. Free-contrast policy reuses its frozen training-only
   profile seed and debits159profilecalls, leaving at most841refitcalls;
   fixed control receives1000. This is a policy comparison, not pure parameter
   causality. No full fits have launched yet. A separate TRAIN-only
   `band_drift_diagnosis/` finds only modest new slope directions and weak RX2
   high-band effective signal support; no drift fit is justified yet. The
   distant+2925Hz contrast basin is not revealed by its local score, reinforcing
   the need for the explicit charged profile proposal. Three finite-gradient,
   curvature and excluded-CFO invariance tests pass for that diagnostic.

## Verification and completion audit

`preservation-check.json` independently rehashes1546 files across15 sealed
manifests, including all600 older outputs and361 iteration3 files. Complete
comparison binds115 input files; null controls bind8 and exactly replay both
saved classifiers. Root-owned new component tests: age2, comparison2, null2.
Agents also own split, diagnosis, catalogue and timing-model tests and receipts.
Older sealed outputs and unrelated tracked changes are preserved.

The actual objective is incomplete: increased development assignment counts
are demonstrated, but a single improved model has not earned broad predictive
and geographic support. S03 gap interpolation is only3windows/one station.
No result here proves transfer to new positions, correct satellite identities,
full DSX01 predictive recovery or the desired position-error reduction.
Keep the goal active. Apply the [validation contract](VALIDATION.md) before
broader existing-corpus DS21/DS22 evaluation; neither dataset is claimed unseen.

No RF collection, production deployment, remote push, scientific fixture change
or unrelated tracked-file edit was performed. Scientific runs use the pinned
runtime and bounded existing-data budgets.
