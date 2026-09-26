# Capture authority: `scan-fw-32a202b6e55630ec`

## Verdict

The saved recording is structurally and cryptographically valid for replay. All 2,214 compressed chunks, all 2,214 decompressed payloads, and the concatenated 21,254,400,000-byte CI16 stream match their declared SHA-256 digests. The canonical manifest digest is `sha256:b381f62da5b5490e43790b69e2947919ad9fee6441b642ac04e7af1be487993a`; the byte digest of the outer seal file is separately recorded and must not be used as the analysis binding.

The full 2,656,800,000-row census found **zero embedded counter words** whose eight stored bytes decode within ±16 samples of that row's authoritative device counter. In particular, the `counter = row coordinate + 2` contamination observed in `scan-fw-4fd51c7c4c1a0273` is absent here. The immutable scan-specific validity mask therefore marks every stored row RF-valid. This conclusion is specific to the tested framing signature; estimator windows must still honor stored visit limits and explicit device-time gaps.

## Coordinates and layout

Each chunk is one visit with 1,200,000 rows at 10 MS/s. A row is four little-endian signed 16-bit values ordered `[RX0 I, RX0 Q, RX1 I, RX1 Q]`, or shape `[sample, receiver, iq]`. For visit `v` and local row `i`:

- compact stored index = manifest chunk `sample_start + i`;
- authoritative device counter = event `valid_start_counter + i`;
- UTC is an uncertain derived coordinate using the manifest's host-bracketed binding, whose first-sample bracket is 364,640,303 ns.

All chunk/event ordinals, compact intervals, and device intervals close exactly. The 2,213 inter-visit gaps range from 3 to 455,883 samples (0.3 µs to 45.5883 ms), total 342,210,412 samples. They remain explicit; compact storage never authorizes closing them. Target populations are 579/563/547/525 for target indices 4/5/6/7.

## RF-row observations

No row contains either signed CI16 rail and the maximum absolute component over the full recording is 263 counts. Exact RX0/RX1 equality occurs on 220,087 rows, at most 179 in any visit; this low-amplitude equality count is descriptive and is not classified as copying or invalidity. No exact repeated 100,000-row block was found. Receipt accounting reports zero transport-missing, unclassified, or unreceived-tail samples. The 343,200,000 transition-invalid samples are outside stored valid visit payloads; there is no manifest evidence for an additional in-payload settling interval.

## Timestamp framing semantics

The current capture adapter copies `upstream.samples` into the visit array unchanged, and the persisted typed reader verifies and reshapes the bytes without classifying or removing rows. A historical contaminated row occupies exactly one normal eight-byte dual-RX sample position while leaving the row count and device axis unchanged. Thus its original RF values are unavailable and deleting the row would falsify time. The saved contract does not attest which firmware/kernel layer wrote such a row, so insertion versus overwrite at that lower layer remains unresolved. Operationally it is a non-IQ overwrite of one stored row, preserving its coordinate.

If a counter word is found in another source, mark both receivers `KNOWN_NON_IQ`, preserve the row, and reject any estimator or transform support intersecting it. Filtering expands invalid support by the complete impulse response. Zero fill is a named sensitivity analysis only.

## Reader handoff

The minimal reader returns immutable C-contiguous arrays: `iq_ci16` (`<i2`, `[N,2,2]`), `valid_mask` (`bool`, `[N,2]`), `source_mask` (`uint8`, `[N,2]`), `device_counter` (`int64`, `[N]`), and `stored_sample_index` (`int64`, `[N]`). It verifies the canonical manifest binding and per-chunk decompressed digest before exposing a visit. Integer counters are subtracted before conversion to seconds.

`source_mask` uses `RF_VALID=1`, `KNOWN_NON_IQ=2`, `UNEXPLAINED_INVALID=4`, `FILTER_TRANSIENT=8`, `STORAGE_GAP=16`, and `SETTLING=32`. The sealed 128-visit cohort is cached once under `/srv/bulk/leo-dev/scan-32a202-phase-replay-cache/selected-visits/`; `cache-index.json` binds every array digest to the selection and validity-mask digests.

## Artifacts and reproduction

- `capture-audit.json`: compact verdict and counts.
- `chunk-integrity.json`: all per-chunk sizes and digests.
- `visit-inventory.csv`: ordinal, target, all coordinates, gaps, and descriptive row statistics.
- `validity-masks/validity-mask-index.json`: immutable half-open invalid intervals (empty for every visit).
- `validity-masks/timestamp-rows.csv`: counter-word evidence inventory (header only).
- `source-provenance.json`: manifest, stream, code, timing, and validity conventions.
- `capture-coverage-contamination.png` and `.svg`: device-time coverage, targets, gaps, and contamination census.

Run with the repository venv and read-only source access:

```text
sudo -n env MPLCONFIGDIR=/srv/bulk/leo-dev/scan-32a202-phase-replay/.mplconfig OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 /home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/capture-audit/audit_capture.py /srv/bulk/leo/scanner-adaptive-recordings/scan-fw-32a202b6e55630ec reports/2026_09_26_scan_fw_32a202b6e55630ec_phase_replay/capture-audit
```

The audit ran at git revision `e1a24b200d4bb68d4f38484dc591e9b9616a2e70` in 156.27 seconds. Component tests: `2 passed`.
