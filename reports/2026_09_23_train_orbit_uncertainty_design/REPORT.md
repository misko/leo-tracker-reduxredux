# TRAIN causal orbit-uncertainty transfer design

**Completed result:** [FINDINGS.md](FINDINGS.md) contains the sealed four-arm
comparison. Orbit-rate flexibility improved RF residuals but did not achieve
sub-300 m positioning and worsened the first group's geographic error.

**Historical design, superseded in part.** See [CURRENT_PROTOCOL.md](CURRENT_PROTOCOL.md)
for the actual pilot's initialization, assignments, clock, and validation rules.
No completed positioning result is claimed by this design document.

## Decision

Reuse the existing causal phase-rate model rather than introduce an arbitrary
age weight. The transferable model is the one in
`tools/fit_causal_orbit_phase_uncertainty.py`: a pre-capture point prediction
plus a signed satellite phase rate multiplied by the candidate's actual TLE
element age, bounded to ±0.25 s/h and regularized by a pre-target temporal
validation scale. A separate constant CFO remains profiled per track. The
receiver clock and the sealed scan epochs remain fixed.

The old numerical prior cannot simply be attached to the new cohort. Its
hyperparameters and selection rule can be frozen, but its 446-satellite history
population followed site-assisted fixed identities. For the blind 151-TRAIN
transfer, rebuild the historical population from the union of blind fixed IDs
and admit only element records whose first archive collection and element epoch
both precede the earliest TRAIN causal cutoff. Use the same candidate prior
classes, reserve the final transition per satellite for temporal validation,
select by validation median absolute phase-rate error, and use the winning
validation RMS as the prior width. No RF residual or location error enters
prior selection.

That relearning is now complete and sealed before any RF fit. All 2,689 blind
fixed NORADs have usable history. The archive supplied 159,624 transitions,
154,246 training transition pairs, and 2,689 final-transition validation
pairs. The unchanged selection rule chose the ridge-feature model at the
prespecified alpha 0.1. Its validation median absolute rate error is 0.03209
s/h and its validation RMS, which becomes the joint-fit prior width, is
0.16029 s/h. This differs materially from the old 0.09177 s/h site-era width
and confirms that the blind-population relearning step was necessary.

## Feasibility

The first six frozen TRAIN scans contain 116 fixed candidate occurrences. In a
bounded 72-hour archive walk, every occurrence has at least four distinct
earlier causal element sets; the median is 10 and the maximum is 17. All 116
have at least two distinct predecessors. Current element ages span 9.38 to
50.56 hours across these scans. Earlier-element ages span 10.26 to 145.79
hours, with median 63.10 hours. The archive therefore has ample local history
to relearn and validate the frozen prior family for this blind population.

The canonical current-element export is
`/tmp/leo-train-orbit-epochs.json`: all 6,988 exact fixed tracks, comprising
2,989 distinct TRAIN `(session_id, candidate_id)` joins over 12 exact
digest/collection snapshot records. Snapshot lookup
must use `(digest, collected_utc_ns)`, because identical content digests can
occur at multiple archive collection records. The first-six inventory follows
that rule and reads snapshots only through `TleArchiveReader`.

## Exact adapter

1. Freeze the 151 TRAIN session IDs, fixed track/candidate IDs, randomized row
   masks, causal snapshot identities, and actual element epochs. Reject any
   VAL/TEST overlap. The primary model uses recorded UTC with scan tau fixed to
   zero.
2. Learn the AR(1) prior once from archive history strictly before the earliest
   TRAIN cutoff, using the existing model family and validation rule unchanged.
   Persist all distinct-element, missing-history, transition, and validation
   accounting.
3. For each fixed candidate and observation time, propagate its exact saved
   causal element at the causal point mean and at point mean ±1 second. Build
   the same quadratic phase-state approximation and verify the final solution
   with exact SGP4. Do not use future elements or a reference receiver
   coordinate.
4. Fit one signed phase-rate parameter per NORAD, shared across every track and
   scan assigned that NORAD;
   this accounts for shared-satellite correlation and prevents track count from
   creating independent orbit parameters. Profile one constant CFO per track.
5. Preserve the existing ±0.25 s/h bounds, 250 Hz smooth robust RF scale, and
   100 Hz prior conversion scale. Report repeated-satellite and all-identity
   modes separately. The all-identity mode remains a flexibility control.
6. Execute the primary pilot on the first six sessions in each frozen TRAIN
   group, separately from Sacramento and Reno priors. Each arm first fits its
   own tau-zero, zero-rate baseline and initializes the matched rate model from
   that arm-local baseline. Full-TRAIN pooled positions do not initialize these
   short views.
7. Retain the existing randomized row masks. Fit CFOs, location, and phase
   rates on fitting rows only. Perturb every held RF row by 1 MHz and require
   fitted location and rates to remain invariant. Whole-group cross-validation
   remains a later, distinct qualification and is not claimed by this pilot.

For a covariance formulation, the same shared rate prior induces
`J_satellite sigma_rate² J_satellite.T` across all rows for a NORAD. Apply the
per-track constant-CFO projection to both data and covariance before GLS. This
uses variation in Doppler shape rather than a constant Doppler offset and keeps
cross-track satellite correlation explicit. It should be evaluated only after
the direct phase-rate transfer establishes exact propagation and conditioning;
it is not a separately tuned weighting model.

## Required implementation changes

The reusable numerical kernels are `quadratic_phase_state`, `robust_residual`,
and `fit_uncertainty`. The old CLI is not directly reusable because it expects
site-era `strict-reranking.json`, episode arrays, a rectangular `Region`, and
old segment IDs. A lean report-owned adapter must instead:

- map `(session_id, track_id, candidate_id)` from the sealed fixed parents;
- read measured values, times, and randomized masks from the existing long
  TRAIN receipts;
- map candidate epochs from the completed public archive export;
- generate exact point/±1-second state arrays from each bound snapshot;
- use track IDs as profiled CFO segments and NORAD IDs as shared rate labels;
- fit a tau-zero baseline independently for every view/prior arm without
  reading a reference coordinate; and
- prove held rows cannot affect fitted parameters by a 1 MHz perturbation test.

No numerical orbit/location fit has yet been run in this audit. The frozen
prior is ready for the authorized adapter execution. The primary comparison
uses recorded UTC and scan tau zero, with matched zero-rate and all-identity
rate objectives. Exact causal propagation is required because the ±0.25 s/h
rate bound times observed element age exceeds the existing ±5-second cache;
clamping or extrapolating that cache is forbidden.

## Evidence and reproduction

`results/first6-feasibility.json` binds the frozen TRAIN inventory, fixed-ID
parent, strict metadata, audit source, and every archive snapshot digest read.
The current-epoch export was produced by the coordinated public-reader helper
in `reports/2026_09_23_train_orbit_age_diagnostic`, avoiding a duplicate full
archive export.

`results/frozen-prior.json` binds the unchanged original learning algorithm,
the final 6,988-track epoch export, strict metadata, this report-owned learner,
and all 589 strictly pre-cutoff archive records. Its SHA-256 is
`c301b762e6b47a2f8c75b8510fdaafa31195179415884a3d857c62e4c7f23f16`.

```bash
uv run ruff check reports/2026_09_23_train_orbit_uncertainty_design/feasibility.py
sudo -n -u leo .venv/bin/python reports/2026_09_23_train_orbit_uncertainty_design/feasibility.py --output /tmp/leo-train-orbit-uncertainty-first6.json
sha256sum reports/2026_09_23_train_orbit_uncertainty_design/feasibility.py reports/2026_09_23_train_orbit_uncertainty_design/results/first6-feasibility.json /tmp/leo-train-orbit-epochs.json
```

The corresponding SHA-256 values are `d55170ec4b7d059db480210587d5f784dd6d1f52a041aec5a233f5203b0f0d6e`,
`22302e34f5ba7df2b2bcd04ad957b29a798fe2b8e27f7fa31ff21be8039041e0`,
and `b0a07a826d99f0880df03e8687e530e074f754c323066c3199a9f8e403ad01c1`.
