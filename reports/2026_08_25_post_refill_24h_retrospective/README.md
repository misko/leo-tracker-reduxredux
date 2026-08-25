# Post-refill 24-hour retrospective dwell review

## Outcome

This report publishes the fixed, read-only review of every committed dwell whose
physical capture start fell in the inclusive interval
`2026-08-24T20:28:52.780539832Z` through
`2026-08-25T20:28:52.780539832Z`. The counter-authoritative continuity-v2
capture profile was already operational before this interval.

The corpus is capture-integrity clean and contains abundant physical
satellite-like activity. It does **not** support a spacecraft association or
tracking claim: every leading identity is either missing a matched control or
fails an available specificity control.

Exact identifiers for all 89 capture sessions and all 89 sealed analysis runs
are listed in [CAPTURE_AND_ANALYSIS_IDS.md](CAPTURE_AND_ANALYSIS_IDS.md). The
same rows, including manifest digests, raw-integrity attestation IDs, release,
lane, seal time, product accounting, and selected branch IDs, are available as
[CSV](capture-analysis-inventory.csv) and
[JSON](retrospective-data.json).

## Integrity result

- 89 committed captures: 80 Standard and 9 Research.
- 89/89 analysis runs succeeded under pipeline release
  `d331df8eaf4f64bfb2cec75e1c664af10aebbdd8`.
- 178/178 radio streams captured exactly 150,000,000 requested samples.
- Every stream has continuity schema v2, `sample_loss_observable=true`, and an
  exact device-counter span.
- Zero gaps, missing samples, overflows, enqueue failures, or terminal rejected
  samples were reported.
- Maximum queue high-water mark was 20 of 32 refills; maximum refill service
  interval was 150.602264 ms.
- Every recording and analysis manifest was rehashed against its PostgreSQL
  digest.
- All 7,031 scientific JSON products were rehashed: 28,529,520,344 bytes, zero
  missing files, size mismatches, or digest mismatches.
- The 12,282 persisted products comprise 10,246 `complete`, 1,882 `no_result`,
  and 154 `partial_coverage` products. Partial products are bounded analyzer
  coverage, not raw capture loss.

The refill discontinuity is therefore observable and absent throughout this
fixed cohort. This does not imply that the RF front ends were calibrated; the
recording manifests generally retain `uncalibrated_prior` frequency authority.

## Descriptive physical census

The automated screen collapses trajectory aliases by branch ID, converts branch
times to absolute UTC, scales degree-1 CFO rates to an 11 GHz reference, and
selects the largest simultaneous path set having at least 2.0 s common overlap
and at most 100 Hz/s normalized slope spread. It is a descriptive screen, not a
calibrated detector or identity test.

| Classification | Dwells |
|---|---:|
| Four-path cross-band | 23 |
| Four-path same-band | 21 |
| Three-path cross-band | 8 |
| Three-path same-band | 8 |
| Two-path cross-band | 3 |
| Two-path same-band | 16 |
| Single-path only | 4 |
| Fragmented/no qualifying multi-path interval | 3 |
| Capture-wide four-path hard null | 3 |

The complete membership of every category is preserved in the identifier
inventory. Research-path products use their research envelopes; partial path
products are admitted only when their sealed dealiased branch inventory is
present.

## Leading physical events

| Capture session ID | Analysis run ID | Main result | Conservative interpretation |
|---|---|---|---|
| `cap-20260825T065355-ba3e4fb8857b` | `capture-fec2f268eb324168853828203b6f72fd` | Four same-band paths, 14.864 s common overlap, 1,806 observations, 11.10 Hz/s normalized spread, 51/64 selected-branch pilot segments | Strongest overall raw event by extent and support. NORAD 62124 is a candidate, not an identity; a whole-catalogue -300 s control exposes orbital-plane degeneracy. |
| `cap-20260825T115401-774be9e8b225` | `capture-c3609bfcf06340f895037f7d4d76f0f6` | Four cross-band paths, 11.825 s, 1,920 observations, 19.96 Hz/s spread, 47/64 pilots | Best balanced cross-band association-shaped event. All four paths rank NORAD 58937 first, but every matched block-permutation control activates. |
| `cap-20260825T103607-9bd90a1a50e4` | `capture-2b2827007f4d477eb80e018c60a51b88` | Three cross-band paths, 8.700 s, 836 observations, 1.91 Hz/s spread, 30/48 pilots | Best RF-normalized coherence. NORAD 66811 is a strong bounded candidate; fixed-target controls activate. |
| `cap-20260825T031521-ec8adc0e9426` | `capture-9e45d8e1810245d890fc1bf93e581d02` | Four same-band paths, 11.000 s, 1,365 observations, 10.02 Hz/s spread, 45/64 pilots | Strong, previously under-emphasized same-band physical event. No qualifying catalogue/control receipt. |
| `cap-20260825T130425-1678069fefd1` | `capture-26248533f2dd4bd193e840ce10a914b4` | Multiple four-path cross-band intervals; the audited opening has 9.150 s overlap, 1,594 observations, 10.77 Hz/s spread, and 46/64 pilots | Excellent physical evidence without qualifying catalogue specificity. The machine inventory separately preserves the longest automatic interval. |
| `cap-20260825T135219-697f458d0037` | `capture-50a995f9874343b7869391d0c1ef144b` | Four cross-band paths over 11.823 s with 1,631 observations | All four path screens rank NORAD 58789 first, but a post-hoc +30 s/NORAD 63280 aggregate is 1.79 cost units better. Specificity fails. |
| `cap-20260825T142817-9949c81ca994` | `capture-0519963f25144300b914f76ce51cc334` | Several long simultaneous cross-band episodes | Best described as a repeated three-path backbone. The strongest RF-scaled pair was selected post hoc and the fourth path is ambiguous. |

The three capture-wide hard-null sessions are:

- `cap-20260825T062228-886fe2dd9cde` / `capture-7f4cf1ae6c7746d1904e579c32b78290`;
- `cap-20260825T105640-facdadeffb3b` / `capture-c0e238da62ad4f95bc76cf8ec8af0053`;
- `cap-20260825T111222-a2d4ce2afb9a` / `capture-d57be1215bc54db3a5d3f8c342c5c9fd`.

## Catalogue and calibration disposition

- `073628` exhaustively evaluates the declared 444-object, 36,408-state finite
  screen and ranks NORAD 58636 first. The acquisition prefix is capped at ten
  candidates per probe and no matched prediction-time controls exist.
- `085623` and `103607` have an exact finite-universe cross-dwell diagnostic
  whose best shared object is NORAD 66811. Both selected contributions fail
  their fixed-target controls; the persisted association correctly has
  `association_claimed=false`.
- `115401` ranks NORAD 58937 first independently on four paths, but all four
  atomic non-affine prediction-time controls activate.
- `135219` fails its wrong-time/confuser comparison.
- The structural-penalty holdout contains 57 certified-null clusters, one real
  RF activation, and one inconclusive cluster. Its best-case one-sided 95%
  false-activation upper bound is 0.0778979, above the 0.05 gate.

Accordingly, this report claims physical multi-receiver RF evidence only. It
does not claim association, tracking, orbit estimation, payload identity, or a
calibrated false-activation probability.

## Related reports and evidence

Self-contained snapshots of the related Markdown reports are in
[`related_reports/`](related_reports/):

- `2026_08_25_065355_satellite_activity.md`;
- `2026_08_25_073628_raw_satellite_activity.md`;
- `2026_08_25_103607_raw_satellite_activity.md`;
- the structural-penalty calibration `README.md`.

Large machine artifacts remain at their original repository or visualization
locations. Their exact paths, byte sizes, and SHA-256 digests are recorded in
[`code/SNAPSHOT_MANIFEST.json`](code/SNAPSHOT_MANIFEST.json).

## Reproduction and archived code

Report-owned census code:

```bash
.venv/bin/python \
  reports/2026_08_25_post_refill_24h_retrospective/code/build_retrospective_bundle.py \
  --hash-json-products
```

Archive the current non-mainline research sources and evidence bindings:

```bash
.venv/bin/python \
  reports/2026_08_25_post_refill_24h_retrospective/code/snapshot_report_sources.py
```

The first command requires read access to the local `leo_tracker` catalogue and
`/srv/bulk/leo`; it invokes read-only `psql` through `sudo -u postgres`. Neither
command writes beneath `/srv` or QNAP.

All known research tools, component cores, component tests, corpus-preparation
code, and visualization builders that were outside the Git-tracked main code
base have been copied under [`code/snapshot/`](code/snapshot/). Mainline
dependencies are instead pinned by repository commit and SHA-256 in the
snapshot manifest. See [SNAPSHOT_NOTES.md](SNAPSHOT_NOTES.md) for the important
historical-byte caveat.
