# DS7 wave 2 artifact integrity review

Scope: read-only metadata and hash audit. No preparation, fit, IQ access, or
source/configuration change was performed.

## Findings

- **Pass — first-eight frozen inputs.**
  `inputs-first8-ready-v1.json` hashes to
  `b348efbcdd00347cef6c66c221948f63fbc78c669c0b3bb0b7ea68e24e4baedc`.
  It contains eight ready and 80 unavailable captures. The first-four frozen
  input remains separately intact at
  `61fb2641ce60ee7062a12f2fb88908b8f4545376083329ce76b19f1209b0f947`.

- **Pass — eligible bank coverage.**
  The eight bank manifests bind to the exact track-export digests recorded in
  the frozen inputs. Their eligible-track counts are 56, 59, 61, 63, 60, 61,
  64, and 62, for 486 total. The two exclusions are explicit frozen-mask cases:
  one no-held track in capture three and one no-training track in capture six.
  The loader-fixed prefix-four receipt records the former and preserves the
  original failed-loader receipt.

- **Pass — failed and repaired loader evidence is preserved.**
  `solver/prefix4-panel-v1` is sealed as the original failed attempt, with its
  input and plan hashes bound to the immutable prefix-four inputs. The
  loader-fixed run is separately sealed and retains the same input and plan
  hashes. Neither receipt was overwritten.

- **Pass — first-eight group membership.**
  `group8-01` has the same ordered eight session IDs as the ready records in
  `inputs-first8-ready-v1.json`. The controls input is deliberately
  first-four-only, matching its four ready records.

- **Pending — group8 execution.**
  `solver/first8-panel-v1` has its frozen inputs, plan, group request, and log,
  but no response, `results.json`, or `seal.json` exists at audit time. This
  review makes no group-eight completion or coverage claim.

- **Pass — scan-estimate source linkage.**
  `coordinator/scan-estimate-provenance-first4.json` binds all four scan
  estimates to sealed independent solver responses. Recomputed seal hashes for
  the listed source runs agree with the provenance entries.

- **Pass — CFO final-receipt chain and restrictions.**
  `FINAL-CFO-RECEIPT.md` explicitly supersedes the earlier README, method and
  lane corrections, and four-window interpretation while retaining prior
  receipts. Its declared final negative-control spec and result hashes match
  the files. It records cumulative use of 163,200,000 bytes and 27.22 seconds,
  the lane exclusion for visit 12, boundary rejection of differential phase,
  and the fixed deterministic negative-control restriction. The receipt makes
  no promotion claim.

## Material gaps

None in the inspected persisted artifacts. Group8 is pending, which is an
explicit execution state rather than evidence of completed coverage.

## Audited artifacts

- `reports/2026_09_27_ds7_wave2/inputs/inputs-first8-ready-v1.json`
- `reports/2026_09_27_ds7_wave2/inputs/inputs-prefix4-ready-v1.json`
- `reports/2026_09_27_ds7_wave2/solver/prefix4-panel-v1/`
- `reports/2026_09_27_ds7_wave2/solver/prefix4-panel-loaderfix-v1/`
- `reports/2026_09_27_ds7_wave2/solver/first8-panel-v1/`
- `reports/2026_09_27_ds7_wave2/coordinator/scan-estimate-provenance-first4.json`
- `reports/2026_09_27_ds7_wave2/cfo/FINAL-CFO-RECEIPT.md`
