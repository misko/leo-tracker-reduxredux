# Host-adaptive capture integration checkpoint, 2026-09-13

This is component integration evidence, not a deployed adaptive scanner or RF
qualification. The fixed native-10M scanner remains in production. No new RF
collection or hardware control was performed for these tests.

## Implemented

- `HostAdaptiveScheduledScannerIntentV4` binds the ten-minute UTC slot, policy
  mode/generation, detector configuration and physical receiver to a durable
  identity. Shadow, adaptive and different detector configurations have distinct
  operation keys. RX selection remains stable across retries.
- `HostAdaptiveHopPlanV2` and `HostAdaptiveHopReceiptV2` bind native 10 MS/s, one
  physical RX, provider wire major 3 and host decision configuration. The plan
  pins a separate 95% qualification duty floor. Its nested published geometry
  retains the existing 90% transport-accounting target; this does not qualify
  adaptive deployment. Old application/wire majors reject the new geometry.
- Every complete visit has source-bound host evidence: exact uint64 counters,
  physical RX, target, configuration digest, six screen scores, at most one blind
  confirmation, support bounds, numerical evidence, worker clocks, feedback call
  clocks, health and disposition. Computation, accepted transport and later HOPS
  decisions remain distinct. Rejected calls and later `not_submitted` results
  preserve the feedback fault. Source-ending results remain explicitly unapplied.
- Detector candidate scalars describe its first candidate; outcome can reflect
  another candidate in the same blind confirmation. The sealed numerical code,
  templates and filter were not changed or tuned.
- `PlutoHostAdaptiveHopRadio` constructs/starts the client, reads IQ, submits
  feedback and restores/closes IIO on one acquisition thread. The caller reads
  a cached clock bracket. A separate worker owns only numerical computation,
  bounded to two CI16 jobs. Overflow records unknown while retaining native IQ.
  Rejected feedback stops further calls; existing provider missing-feedback
  policy is responsible for uniform fallback. Tests do not prove live fallback
  timing. Native read-ahead exhaustion instead fails capture explicitly.
- `HostAdaptiveHopIqManifestV2` stores four CI16 bytes per native time sample,
  one payload column for either RX. Eight chronological visits contain 9.6
  million samples / 38.4 MB, with no implied uniform sweep. The pinned store
  dispatches closed majors and verifies compressed/uncompressed hashes and UTC
  timing. Legacy manifests remain unchanged; queued compression handles both.

## Validation

The focused suite passed **285 tests**, including existing storage history,
overview and analysis-source consumers. The new tests cover both RXs/modes,
repeated target order, complete/cancelled receipts beyond 2^53, full chunks and
partial tails, exact CI16 extrema, immutable arrays, mixed-major discovery,
corrupt identity/timing/byte counts, missing decisions, worker failure,
overflow, rejected feedback, startup failure and IIO ownership. They use fake
clients and short computation delays, not network radios.

```sh
.venv/bin/python -m pytest -q --tb=short \
  tests/scanner/test_host_adaptive_contracts.py \
  tests/scanner/test_adaptive_hop_contracts.py \
  tests/scanner/test_single_rx_profile.py tests/scanner/test_scanner_schedule.py \
  tests/storage/test_host_adaptive_hop_store.py tests/storage/test_adaptive_hop*.py \
  tests/radio/test_host_adaptive_mapping.py tests/radio/test_pluto_host_adaptive.py \
  tests/radio/test_pluto_adaptive_hop.py tests/radio/test_host_decision_worker.py
```

Use the existing development environment without replacing its custom IIO
dependencies. Ruff, mypy for the eight changed production integration modules,
and `git diff --check` also passed for this checkpoint.

Read-only production observations: 18:30 and 18:40 fixed scans each published
2,386 visits, at 954,087 and 954,318 ppm valid duty. Acquisition still selected
`1212242843055e7e4079143ab1940532e8ac76fd`. The global acquisition lease was
respected; no other radio or lease owner was changed.

## Remaining before deployment

1. Connect these ports/producer/store through application lifecycle and scheduler
   dispatch. Persist/retrieve V4 intent with its exact operation key and reject
   incompatible flags instead of falling through to fixed capture.
2. Extend native-10M actual-visit analysis, checkpoints/products, refinement and
   trajectory/TLE readers, API/presentation and generated web assets. Legacy
   consumers passing tests does not establish support for new recordings.
3. Package and verify the compatible provider, PPU, host library, detector,
   templates and filter. Bind the adapter's release-supplied engine factory to
   the detector manifest digest recorded in the intent and plan.
4. Run four reserved bounded live canaries on only
   `104000bac4950008230026001b440a003a`, then switch between scheduled scans and
   verify the first adaptive scan through analysis and browser output. The RF
   ledger is unchanged: 237.331441 seconds charged, 1,562.668559 remaining,
   including 1,500 reserved for these five runs.

The full deployment goal remains incomplete. No production profile, release
selector, firmware or scientific golden fixture was changed in this checkpoint.
