# Plan for correcting PNT Kalman V3 acquisition

Date: 2026-08-25

## Decision

Freeze V3 exactly as published and implement the correction as an additive,
research-only V4.  V3 is exported, source-hash-bound in replay evidence, and
covered by tests that intentionally preserve its current rolled-control
behavior.  Editing V3 in place would change the meaning of existing results.

V4 should compose a new seeded, multi-mode acquisition stage with the unchanged
phase-safe tracking core configured by `PilotPntKalmanConfigV3`.  It must not
alter Standard analyzers, persisted V1--V3 contracts, phase thresholds, or
golden fixtures.

This follows the acquisition-then-local-tracking separation used by Qin et al.
in [*Pilots and Other Predictable Elements of the Starlink Ku-Band
Downlink*](https://arxiv.org/abs/2602.02627) and by Kozhaya, Saroufim, and
Kassas in [*Unveiling Starlink for
PNT*](https://navi.ion.org/content/72/1/navi.685).

## Small, composable API

Add a new infrastructure-blind module,
`src/leo/analysis/starlink/seeded_acquisition.py`, with four immutable result
types:

- `KnownPilotModeSeed`: epoch, CFO, optional CFO rate, uncertainty/search
  bounds, trajectory branch ID, CFO-alias lift, and provenance digest.
- `SeededPilotAcquisitionConfig`: block geometry, proposal/candidate/component
  bounds, local/global domains, symbol partitions, control-template digests,
  and optional calibration-receipt digest.
- `KnownPilotModeCandidate`: proposal origin, epoch/CFO/rate, block evidence,
  held-out exact and control scores, prior distance, alias class, consistency,
  component-set membership, and truncation metadata.
- `KnownPilotModeAcquisitionResult`: every retained mode plus independent
  presence, code-specificity, alias-resolution, and uniqueness decisions.

Expose two entry points:

```python
acquire_seeded_known_pilot_modes(...)
analyze_contiguous_pilot_pnt_kalman_v4(...)
```

`PilotPntKalmanConfigV4` should contain a seeded-acquisition configuration and
an unchanged V3 tracker configuration.  `PilotPntKalmanV4Result` should contain
the acquisition evidence and one independent phase-safe track per surviving
mode.  Persisted V4 research artifacts need a new schema/config digest; no
existing serialized type changes.

## Acquisition algorithm

1. **Always propose the supplied seed.** Sparse top-K retention must never
   erase the trajectory-conditioned epoch/CFO mode.
2. **Use four approximately 20 ms blocks across each 75 ms window.** Start with
   epoch +/-2 samples and CFO +/-500 Hz in 50 Hz steps around the seed.
3. **Respect the non-integral frame lattice.** Map each block to
   `e0 + round(k * sample_rate / 750) - block_start`; do not cluster naively
   rounded modulo-frame coordinates.
4. **Split fitting from prediction.** Propose geometry on anchor/even Qin
   symbols and validate it on odd Qin symbols using the same absolute received
   samples.
5. **Condition every control on the exact candidate.** Score rolls 17/53/101
   and predeclared orbit-breaking controls at the exact epoch/CFO.  Include
   deterministic per-subcarrier derangements and opposite-edge states mapped
   to the tested tones, with template digests in the result.
6. **Aggregate repeated evidence.** Require bounded epoch span, CFO dispersion,
   exact evidence, and same-coordinate control margin across blocks.  Re-score
   a surviving consensus mode jointly on the whole window.
7. **Use one bounded global fallback only when the seed is unsupported.** Keep
   fallback proposals explicit; do not silently replace a supported seed.
8. **Rank by held-out exact evidence.** Specificity margin and prior distance
   are gates/tie-breaks, not the primary maximum.
9. **Canonicalize CFO aliases before component counting.** Quotient candidates
   modulo `227,272.727273 Hz`, retain the alias lift as metadata, and never call
   alias copies separate signals.
10. **Keep resolvable modes separate.** Track a genuine approximately 85 kHz
    pair as two candidates rather than widening one Gaussian state.
11. **Run the existing phase-safe tracker independently per mode.** Acquisition
    recovery must not relax phase qualification or smooth through a mode jump.
12. **Report ambiguity truthfully.** A cyclic roll plus compensating epoch shift
    is `code_phase_ambiguous`, not `no_signal`.

Do not add a CFO-rate search initially.  Rate may center the block CFO prior,
but the frozen experiment's median score change from dechirping was only
0.000156, so a new rate dimension is not the correction.

## Development sequence

### 1. Freeze contracts and baselines

- Bind the V3 source, configuration, frozen-corpus, and current report hashes.
- Run and retain every existing V3 acquisition/tracker test unchanged.
- Record current V3 runtime, work counters, memory, and all 537 capture rows.

Exit criterion: old V3 exports, tests, and serialized evidence are unchanged.

### 2. Build the acquisition primitive

- Implement protected seed proposals, lattice-correct block consensus,
  same-coordinate controls, deterministic ordering, alias canonicalization,
  global-fallback accounting, and bounded multi-mode results.
- Keep the module free of storage, PostgreSQL, HTTP, CLI, and concrete adapter
  imports.

Exit criterion: focused unit/property tests cover every candidate origin,
decision, and truncation path.

### 3. Compose V4 tracking

- Add the V4 config/result and run the unchanged phase-safe core at each
  retained mode.
- Reset all states between caller-qualified continuity segments.
- Keep phase, presence, specificity, alias, and uniqueness decisions separate.

Exit criterion: at a fixed epoch/CFO mode, V4 tracking is numerically identical
to the V3-core result.

### 4. Calibrate without touching Standard

- Create source-bound manifests for synthetic, adversarial, real-IQ, canary,
  and untouched-holdout units.
- Split by complete capture/dwell so overlapping windows never cross
  calibration and test partitions.
- Freeze control templates, thresholds, and search bounds before the holdout
  run.

Exit criterion: one immutable configuration and calibration receipt can replay
every decision with complete population accounting.

### 5. Shadow research rollout

- Add V4 only to the opt-in research analyzer.
- Run V3 and V4 side by side; persist both without rewriting prior artifacts.
- Propose Standard integration only after the promotion gates below pass.

## Test matrix

| Layer | Required coverage |
|---|---|
| V3 regression | All existing V3 tests and exports unchanged |
| Contracts | Validation, immutable ordering, digests, caps, and exact truncation accounting |
| Frame lattice | Epoch 0/3333, 3333/3334 progression, and block-to-capture conversion |
| Positive synthetic | CFO/SNR/SFO/rate sweeps, arbitrary frame phase, modulo-pi signs, large seed error, and qualified discontinuity |
| Held-out split | A strong even-only decoy is rejected by odd Qin; exact/control use identical absolute samples |
| Metamorphic | Joint sample/epoch shift invariance, alias quotient invariance, and roll/epoch ambiguity |
| Null/adversarial | Gaussian, colored, impulsive, tones, wrong edge, deranged code, zero/short/nonfinite inputs |
| Candidate pressure | More than eight anchor decoys cannot remove the forced seed; all truncation is reported |
| Mixtures | Alias copies collapse; two non-alias components remain separate; near-collinear mixtures report ambiguity |
| Tracker | Per-mode V3-core parity and no phase-threshold relaxation |
| Tools | Frozen population accounting, deterministic/resumable JSON, and same-mask causal comparison |

## Frozen-capture regression gates

Use `cap-20260825T150802-473cb5bbcbd6` as a development canary, not calibration
truth.  Across all 537 windows V4 must:

- preserve numerical tracking for all 53 Standard-qualified and all 55
  V2-phase-qualified controls;
- surface and track 50/50 robust V3 acquisition losses;
- avoid publishing the seven one-update CFO aliases as independent tracks;
- select and track 0/57 matched alias/null peers under the frozen block policy;
- account for every proposal, fallback, component, and rejected row; and
- leave phase thresholds unchanged, reporting any newly passing phase case for
  explicit review rather than automatic promotion.

Historical August-22/August-24 cohorts are regression evidence.  After the
configuration is frozen, evaluate at least ten previously unused, same-release,
estimable dwells from the existing corpus.  Compare V4, V3, and the causal
trailing-20-ms line on identical masks, aggregating by dwell rather than by
correlated frame.

## Calibration and performance gates

Calibration must cover the entire proposal/search/adjudication process.  The
existing 64 Gaussian windows are only a smoke test.  For a target event rate no
larger than 0.001, zero events require at least 2,995 genuinely independent
null units for a one-sided 95% bound.  Standard consideration additionally
requires an authoritative labeled real-IQ absence corpus; unlabeled or
overlapping windows cannot substitute for it.

Record work counters in every result and publish reproducible performance
artifacts.  After measuring the V3 baseline, require:

- seeded-path p95 runtime no slower than V3;
- full-537 wall time and peak RSS no more than 1.25 times V3;
- bounded fallback/component inventories; and
- NumPy/native parity within declared tolerances.

Wall-clock limits belong in benchmark reports, not flaky CI assertions.

## Promotion ladder

1. **Experimental V4:** unit/property tests, V3 regression, capture canary, and
   performance bounds pass.
2. **Research candidate:** the frozen configuration passes untouched-dwell
   validation and calibrated synthetic/adversarial controls.
3. **Standard proposal:** real-IQ null calibration, preregistered same-release
   evaluation, innovation/NIS checks, scientific review, and a new versioned
   Standard contract/release all pass.

At no stage should prior V3 artifacts be rewritten or golden fixtures updated
merely because V4 differs.

## Explicit non-goals

Satellite identity, TLE association, payload decoding, absolute carrier phase,
pseudorange/transmit time, automatic reset discovery, phase-threshold
relaxation, new RF collection, and representing multiple signals inside one
Gaussian tracker are outside this correction.

## Supporting evidence

- [V3 acquisition-model audit](2026_08_25_150802_v3_acquisition_model_audit.md)
- [V3 missing-signal investigation](2026_08_25_150802_v3_missing_signal_investigation.md)
- [Full-dwell V3 replay](2026_08_25_150802_v3_full_dwell.md)
- [Original V3 comprehensive review](2026_08_25_pnt_kalman_v3_comprehensive_review.md)
