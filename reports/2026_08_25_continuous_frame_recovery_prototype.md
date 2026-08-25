# Continuous frame-recovery prototype

Date: 2026-08-25

## Outcome

The gaps in the earlier Kalman plots were primarily gaps in replay coverage, not
missing samples in the recording and not ordinary Kalman dropouts. Each 100 ms
bin selected its strongest 20 ms GLRT probe and then began a 100 ms replay at
that moving probe position. Across the three prescribed 500 ms intervals, those
seed-started windows covered only 81.667% of the source timeline.

This prototype instead reads each prescribed interval on a fixed, gap-free
sample grid and independently reacquires inside every refill-safe segment. It
recovers 129 of 131 frame opportunities in the regions that were visibly blank
in the earlier plot. The other two opportunities straddle application refills
and are deliberately rejected rather than interpolated.

The recovery result is strong, but the new two-state CFO/rate filter is not an
accuracy improvement over the causal trailing-20-ms robust frame-CFO line. On
the common 498-frame post-acquisition mask, its pooled RMS is 46.944 Hz versus
46.482 Hz for the line, a ratio of 1.0099. It wins one of three dwells. The
recovery machinery is therefore worth retaining as a research prototype; the
filter dynamics are not ready for promotion.

## Prototype design

The implementation is additive and does not change the persisted V1, V2, or V3
contracts.

- Read one fixed 500 ms IQ interval for each of D1, D2, and D6.
- Treat every application refill as a hard state and continuity boundary.
- Select the strongest safe, complete, sealed 20 ms GLRT64 candidate separately
  inside each refill-safe segment.
- Project the exact 750 Hz frame lattice backward and forward from that anchor,
  preserving the 3333/3334-sample cadence.
- Represent the full 1/750 s = 1.333333 ms epoch as a discrete acquisition
  branch; never place the full ambiguity in one Gaussian timing state.
- Record one explicit outcome for every anchor-owned frame opportunity and keep
  unanchored sample spans separate.
- Use even Qin symbols to qualify and update a causal two-state `[CFO, rate]`
  filter. Use odd Qin only for a post-anchor, pre-update conditional score.
- Permit at most two prediction-only coasts; the third consecutive miss becomes
  `LOST`. Never bridge a refill, source/alias mismatch, or confirmed epoch jump.
- Keep phase feedback disabled. This bounded prototype does not estimate phase
  and makes no carrier-phase navigation claim.

The source/alias identity of each local anchor is intentionally unknown, so no
state is transferred between independently acquired segments.

## Three-dwell result

Ratios below one favor the recovery filter. The accuracy rows begin only after
the all-Qin 20 ms acquisition probe has ended and use the same frames for both
models.

| Dwell | Fixed read | Old replay union | Supported / opportunities | Recovered in prior gap | Filter RMS (Hz) | 20 ms line RMS (Hz) | Ratio |
|---|---:|---:|---:|---:|---:|---:|---:|
| D1 | 100% | 80% | 353 / 358 | 55 / 56 | 48.513 | 47.228 | 1.027 |
| D2 | 100% | 80% | 369 / 374 | 37 / 37 | 46.550 | 49.121 | 0.948 |
| D6 | 100% | 85% | 369 / 375 | 37 / 38 | 45.664 | 43.328 | 1.054 |
| Aggregate | 100% | 81.667% | 1091 / 1107 | 129 / 131 | 46.944 | 46.482 | 1.010 |

The 1,107 denominator contains anchor-owned opportunities only. Another 58,624
samples are explicitly unanchored: a 22.2784 ms tail in D1 and a 1.1712 ms head
in D2. The opportunity ledger contains 1,091 even-training-supported and
filter-accepted frames, 14 refill-crossing rejections, and two incomplete
capture endpoints. The latter two are labeled as prediction-only coasts and are
not counted as estimator support.

The robust all-Qin diagnostic supported 1,072 frames, 19 fewer than the even
training fold. That difference is useful evidence that a single all-symbol
coherence gate can discard otherwise usable frame-frequency measurements.
However, occupancy is not independently labeled, so `1091 / 1107` must not be
reported as conditional estimator retention or signal occupancy.

## Interpretation

The plot gaps can be removed without inventing measurements. A fixed read grid,
explicit frame-opportunity ledger, exact lattice projection, and refill-local
reacquisition recover nearly all of the previously skipped regions. Remaining
breaks now mean something concrete: a refill-crossing frame, an incomplete
endpoint, or a segment with no safe acquisition anchor.

The Kalman dynamics remain the weak part. Their common-mask result is a slight
loss both when frames are pooled (1.0099) and when dwell ratios are combined by
equal-dwell geometric mean (1.0086). The next experiment should retain this
recovery front end but compare the two-state filter against either the existing
causal robust line or a hybrid whose process noise and innovation gates are
calibrated from independent continuity arcs.

## Scientific limits

- These are three predeclared exploratory intervals, selected to include prior
  visible gaps, not an untouched production-promotion cohort.
- Frame recovery before the local anchor uses buffered IQ and backward lattice
  projection. It demonstrates recoverability, not zero-latency online behavior.
- Odd-Qin error is delayed-causal at the frame estimator, but conditional on an
  all-Qin GLRT64 anchor selection. It is not end-to-end untouched validation.
- Source, trajectory, and CFO-alias identity are not yet bound across refills;
  each segment therefore resets independently.
- No independent occupancy fold exists, and no inactive-frame claim is made.
- Phase is neither estimated nor fed back in this module.
- Production evaluation still requires a frozen configuration and at least ten
  untouched, same-release dwells with source/alias binding, mirrored rolled-Qin
  controls, reacquisition latency, and calibration/coverage diagnostics.

## Reproduction and evidence

Run the verified read-only replay from the repository root:

```bash
uv run python tools/prototype_continuous_frame_recovery.py
```

Run the component-owned tests:

```bash
uv run pytest -q \
  tests/analysis/test_continuous_frame_recovery.py \
  tests/analysis/test_continuous_frame_recovery_tool.py
```

Persisted artifacts:

- `reports/figures/2026_08_25_continuous_frame_recovery_prototype/continuous-frame-recovery-summary.json`, SHA-256 `28119707ca7adf5f089021cab0613abf142f3e3953c63a6b1193f38eda10f058`.
- `reports/figures/2026_08_25_continuous_frame_recovery_prototype/continuous-frame-recovery-rows.json`, SHA-256 `613d4bfb90d985b1582860443fc7569bbf2c75b1453d418bcc733430830a5e04`.
- `reports/figures/2026_08_25_continuous_frame_recovery_prototype/continuous-frame-recovery-three-dwell.png`, SHA-256 `3ef3aed2ce96140dd9cf38a334094eefb2e36544dd799ee1b3b3817cf959679e`.
- Frozen input declaration, SHA-256 `25ec6b5212110ff9bd14809ed0fced93d8a0cd0af1288e504265e6385daeb740`.
- Recovery core, SHA-256 `132f3d517db6fe0bee169c29a5726b26721e6b871479fffd1571b5297610b58b`.
- Replay/render tool, SHA-256 `0fc91364431f9c979f752385d82f6a790d4091031b72c180b014b3b5b1f57db0`.

The evidence document embeds and verifies the pinned recording manifests,
pilot scans, sealed seeds, timelines, gap maps, scope bindings, and compressed
IQ chunks used for all three intervals.
