# Native 1.25 MS/s partial-band analysis

The low-rate lane is additive and experimental. It does not change RF collection,
firmware, the higher-rate detector, or published legacy contracts. A capture's
reported LO remains reported metadata, not independent proof of live PLL tuning.

## Scientific model

`filtered-pilot64-grouped-glrt-v1` synthesizes the published pilot waveform at
5 MS/s, applies trial CFO, then filters and samples at 1.25 MS/s. The approximate
receiver model is a 129-tap Kaiser-beta-8 low-pass at 550 kHz. Neighboring symbols
are included through the filter support; out-of-band tones are not aliased back
into the template. Fractional frame/symbol sampling is modeled explicitly.

The score is a normalized matched-projection GLRT-style statistic with independent
unknown complex amplitudes per frame. Scores and thresholds are **not** the same
as the existing full-band GLRT64 margin. The model does not claim an analytic
field false-alarm probability or calibrated CFO uncertainty.

Every 20 ms probe uses 14 complete opportunities, split reproducibly into seven
training and seven evaluation frames. Training uses pilot symbols 18–81;
evaluation uses independent symbols 146–209 and freezes the acquired CFO/epoch.
The source/configuration/probe identity seeds the grouped split. A randomized
symbol-sequence control receives the same coarse search budget. The gates are
training score >= 0.025, evaluation score >= 0.02, and evaluation >= three times
the larger of conditioned and independently searched control evaluation scores.
These gates publish **candidates**, not satellite identities or positions.

Search covers +/-800 kHz with a 2 kHz coarse bank and 100 Hz local CFO grid;
timing refinement uses 0.125-sample steps. Three separated frequency basins are
retained. Grid resolution is not a measurement uncertainty. CFO associations stay
separate by channel, edge, and receiver; plotted lines never bridge retunes.

## Replay and products

Run with the release's Python environment and source path:

```sh
python -m leo.cli.partial_band --bulk-root /srv/bulk/leo \
  --session-id scan-fw-5248143e8ece71d7 --maximum-workers 4 --maximum-seconds 560
```

Use `--output-root` for an isolated rehearsal. Each invocation is bounded;
rerunning resumes verified visit checkpoints. The default covers every retained
visit on both receivers with non-overlapping 20 ms probes. A missing or corrupt
checkpoint cannot satisfy completion. Products are configuration/source-addressed
under the component-owned `scanner-partial-band-glrt-v1` namespace.

A sealed publication requires `coverage.png`, `glrt64-response.png`,
`cfo-trajectories.png`, `bandwidth.png`, `probes.jsonl.gz`, and `segments.json`.
All probe outcomes, including non-detections, are retained in the download.
`PartialBandStore.import_completed` verifies and publishes a rehearsal through
the store ports without constructing or modifying capture paths.

Read-only status is exposed at
`/api/v1/scanner/adaptive-sessions/{session_id}/partial-band`, with the required
`input_manifest_sha256` query. Artifact requests additionally require their
published digest. Corrupt evidence returns 409, not an empty successful result.
The native-low-rate scan page displays this lane instead of the unsupported
full-band/phase/position panels. Reads never enqueue work.

The shared queue dispatches the new lane by its source/configuration digest.
Completion requires verified artifacts, not worker stdout alone. Low-rate results
do not enqueue unqualified phase or positioning stages. Existing higher-rate
processing and the deployed v15 tracking overlay remain unchanged.

## Validation and rollout

- Independent 10 MS/s synthetic fixtures test both edges, fractional timing,
  +/-799.3 kHz offsets, filter mismatch, Doppler rate, and missing verification
  symbols. FFT search is checked against direct filtered projection.
- Zero energy, non-finite inputs, colored noise, and unmodulated carriers are
  tested. Storage tests cover interruption/resume, immutable products, complete
  inventories, publication import, digest mismatches, and missing artifacts.
- `tools/qualify_partial_band.py` runs bounded filtered-noise trials and a seeded
  paired 2.5-to-1.25 MS/s saved-IQ panel. Keep all disagreements, including
  frequency-boundary cases; separate recordings are not paired comparisons.
- Rehearsal `scan-fw-5248143e8ece71d7` covers 2,215 dwells / 26,580 probes. The
  initial complete run produced 21,862 candidate-bearing probes. This is not a
  satellite count or a sensitivity/false-alarm estimate.
- The 1,000-trial filtered-Gaussian-noise experiment produced zero passing
  candidates. That finite test does not establish a field-wide false-alarm rate.

Stage overlays with `tools/stage_partial_band_release.py` against the **current**
API/worker parent, preserving worker memory fixes and native-capture readers.
Rebuild and test the web bundle after reconciling any newer deployed changes.
Record the staged source hashes, verify imports under both production interpreters,
and test a complete canary through HTTP and the browser before enabling enqueue.

Install new API/worker/queue drop-ins without changing capture services. Restart
analysis workers before enabling low-rate queue admission. Verify a real queued
job reaches verified publication and that higher-rate views remain accessible.

Rollback removes only this deployment's drop-ins and restores the recorded parent
API/worker/web pins. Retain all source-bound products and capture IQ. Drain or pause
this lane's queued jobs before reverting workers, since older workers do not
understand its dispatch identity. Do not roll back by deleting products or by
rewriting capture manifests.
