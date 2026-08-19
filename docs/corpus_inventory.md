# Real-IQ corpus inventory

Audit date: 2026-08-19 UTC

This is a read-only inventory of candidate regression inputs in
`/mnt/qnap01`, `leo-tracker`, and `leo-tracker-redux`. No IQ was copied and no
source file was modified. `corpus/manifest.example.json` records the proposed
members without asserting that their future local payloads already exist.

The reference revisions inspected were:

- `/home/mouse9911/gits/leo-tracker` at
  `0bb80d14759fd8496b74e7d3219a690be18565a6`. Its working tree had unrelated
  pre-existing changes in tests and `uv.lock`; this audit did not modify them.
- `/home/mouse9911/gits/leo-tracker-redux` at
  `b2b8827832715f7cd45196cd08919bcc5dd2a3f0` with a clean working tree.

## Proposed corpus

`REQUIRED` means the first useful vertical slice should fail if the locally
materialized fixture is absent or has the wrong digest. `PLANNED` means the
source or its scientific role is intended for possible future promotion but is
not ready for that gate. `UNAVAILABLE_HISTORICAL_EVIDENCE` means an expected
historical object is retained in the inventory for provenance and possible
exact-byte recovery, but is non-executable and cannot count as present or
passing. All future local copies must be tagged `TEST` and permanently held
from retention.

### REQUIRED: RETRO known-pilot candidate window

- Fixture ID: `retro-positive-68p7`
- Role: numerical acquisition/QAM regression on real sky IQ.
- Source object:
  `/mnt/qnap01/mouse9911/leo-store/2026_08_17_RETRO_QAM/raw/clip-002.ci16`
- Source size: 500,200,000 bytes.
- Source SHA-256, reverified during this audit:
  `6d105ae645c0ac91e0e93ebc4ac5b456890025ebfb9bb9e1344423dc27c7c3fa`.
- Selected range: byte offset 304,000,000, byte count 200,000; equivalently
  25,000 dual-receiver samples beginning at sample 38,000,000 in the clip.
- Selected SHA-256, reverified during this audit:
  `a80c3b0d94b95548d9ae0ab5d8243fee8cf6c760ccb6fa4ca4efeb6351176e50`.
- Geometry: little-endian `int16`,
  `(sample, receiver, component)`, two receivers, I/Q component order,
  2.5 MS/s. The selected interval is original recording time
  68.700--68.710 seconds.
- Truth/status: candidate evidence for the published Qin edge synchronization
  pilot. It is not a calibrated detection and contains no decoded payload.
- Provenance root:
  `/mnt/qnap01/mouse9911/leo-store/2026_08_17_RETRO_QAM`.
  `provenance/manifest.json` is 5,558 bytes with SHA-256
  `37500e3620fc9795eca3847626e308a24def601bfafa50f8311d868b465b0236`;
  `oracle/followup.json` is 5,975,011 bytes with SHA-256
  `89b901207ed6e3c3dbde531d6dc60b9b0a498677065e51c8cbe6fa71a3b37002`.
- Availability: source and selected bytes are present; no local fixture has
  yet been materialized in the new project.

This should be the first required detector fixture because it is small after
selection, has independently frozen input and oracle hashes, and already has
native Redux parity. The acceptance values remain candidate-only: epoch 2,063
on both receivers; CFO +364,150.8476787003 and -194,343.8743595247 Hz;
individual hard-symbol accuracy 0.7483333333333333 and 0.7991666666666667;
combined historical accuracy 0.88375.

### REQUIRED: synchronized same-tuning, two-radio ingest pair

- Session ID: `sync-same-l-ch1-lower-20260814T001700Z`.
- Role: real four-receiver ingestion, synchronization metadata, power,
  waterfall, CLI, API, and browser regression. It is not detector truth.
- Source metadata:
  `/mnt/qnap01/mouse9911/leo-scans/sync-20260814T001700Z/sweep.json`,
  2,418 bytes, SHA-256
  `a1751c753a65a6ef482852ce25671d98f5be9b53b7424614e15ec729460c6de2`.
- Radio `pluto-19f2` source:
  `/mnt/qnap01/mouse9911/leo-scans/sync-20260814T001700Z/pluto-19f2.ci16`,
  12,800,000 bytes, SHA-256
  `f5949cd80bcd06760caa386065c6a9bb1dd09fd83a3a28de76684c413342a6fb`.
- Radio `pluto-5d4d` source:
  `/mnt/qnap01/mouse9911/leo-scans/sync-20260814T001700Z/pluto-5d4d.ci16`,
  12,800,000 bytes, SHA-256
  `2189ebc2672f5d3fd516e50684bda124a3f85a432219c91a60b2156b969cf6bf`.
- Selected range in each radio object: byte offset 0, byte count 1,600,000;
  tuning index 0, CH1 lower edge, 200,000 samples, 80 ms, two receivers.
- Selected SHA-256 values, reverified during this audit:
  `ae6b124fff2668fa80fba1af9da98e7ffcb2df9cd3b6e196c8d761f4b25ba031`
  for `pluto-19f2` and
  `4dde4726bd0f4eef06b904e75a69f3c61150b0d1fdd273f526297817a7120e42`
  for `pluto-5d4d`.
- Geometry: source layout
  `(tuning, sample, receiver, component)`, shape `[8, 200000, 2, 2]`,
  little-endian `int16`, 2.5 MS/s. A materializer may extract tuning 0 into
  two standard `(sample, receiver, component)` radio streams without changing
  sample bytes.
- Synchronization status: both radios used the same arm and tuning order. The
  recorded tuning-0 barrier-release skew is 0.0376 ms. It is a lower bound,
  not measured first-sample skew; actual overlap must not be invented.
- Truth/status: `unlabeled_sky`, `target_present=null`, accuracy-ineligible.
- Availability: source metadata and both selected byte ranges are present; no
  local fixture has yet been materialized.

This pair is intentionally only 3.2 MB of IQ. It exercises the honest
two-radio session model while avoiding the 76.8 MB six-recording development
set and the roughly 1.14 TB full synchronized-scan source.

### UNAVAILABLE_HISTORICAL_EVIDENCE: J1 known-pilot window

- Fixture ID: `j1-calibrated-positive-41p6`.
- Expected source path:
  `/home/mouse9911/.local/share/leo-flow/objects/sha256/23/23cceb3a5223180ff92398214125513d4c32cc541ec1ae5b7c4c28fba5bbcc8c`.
- Expected source size: 1,200,000,000 bytes.
- Expected source SHA-256:
  `23cceb3a5223180ff92398214125513d4c32cc541ec1ae5b7c4c28fba5bbcc8c`.
- Selected range: byte offset 832,000,000, byte count 200,000; expected
  selected SHA-256
  `4fbd775f850124dab038e70dadba1ce1cbbfc16ebe58d9fb425430b51d61ce02`.
- Geometry: little-endian dual-receiver CI16 at 2.5 MS/s, selected recording
  time 41.6--41.61 seconds.
- Historical report role: strong candidate evidence for the known pilot, not
  executable fixture truth and not a calibrated detection.
- Availability: **missing**. The exact expected CAS path does not exist, and
  no copy was found in the audited `/srv/bulk`, local leo-flow object store, or
  documented QNAP archive paths. This inventory does not claim the IQ exists
  elsewhere. It must not be executed, reported as passing, or silently
  omitted. Only a separately reviewed recovery matching the expected
  complete-object and selected-window hashes can propose changing this state.

The calibration source named by the frozen fixture is
`/mnt/qnap01/mouse9911/leo/reports/lnb-calibration.json`, expected SHA-256
`141a489a08f236839cd1cbec8d31cc31611abd5941b91bca7269974b53d17f8d`.
The path exists, but its current 950-byte content hashes to
`7b9db0551e8c6520ae18e81d89c90459464ce558fc791ff07bf5ae77149c659d`.
Therefore the frozen calibration artifact is also not presently available by
its asserted digest. Do not bless the current mutable path as an equivalent
artifact without an explicit provenance review.

The targeted follow-up audit, including exact CAS, historical catalog,
temporary artifact, QNAP archive, recycle/snapshot, and calibration evidence,
is recorded in [`j1_recovery_audit.md`](j1_recovery_audit.md). It recovered no
raw J1 bytes. The project owner accepted ADR 0006 Option B on 2026-08-19, so
the declaration now preserves J1 as non-executable
`UNAVAILABLE_HISTORICAL_EVIDENCE` and makes no J1 parity,
calibrated-detection, or specificity claim.

### PLANNED: historical control interval

- Fixture ID: `retro-control-39p75-first-10ms`.
- Source:
  `/mnt/qnap01/mouse9911/leo-cropped/evidence-v2/ch4-lower-edge-narrow-pluto-5d4d-20260813T211014Z/clip-001.ci16`,
  10,000,000 bytes, SHA-256
  `674e89f03a766ad3783593c356d746887fc18af2bb66147ce9b43f4b4139a689`.
- Candidate range: byte offset 0, byte count 200,000, selected SHA-256
  `d50ffe260b16dd04741e2eafbb624c6dcd1ca67f0349f3da1d7918e4765954cd`.
- Provenance calls the containing 0.5-second interval a
  `deterministic_control`, but this is still real, unlabeled sky. It is not an
  independently established signal-absent negative and must not be used to
  claim specificity. Promote it only for control-path or UI comparison after
  that limitation is encoded in the test contract.

## License and handling

No `LICENSE`, `COPYING`, or `NOTICE` file was found at the roots of either
reference repository or the two audited QNAP corpus roots. The data was
produced by this project's hardware and is suitable for internal project
regression under the owner's direction, but redistribution/publication terms
are not stated. Record the license as `NOASSERTION` and do not publish corpus
bytes outside this project until the owner assigns terms.

QNAP is a read-only provenance source. Future materialization may read a named
object or byte range and write a new protected local object under `/srv/bulk`.
The new project must contain no operation that deletes, moves, renames, or
rewrites a path below `/mnt/qnap01`. Source and selected digests must be checked
before publication of a local fixture.

## Numerical code and reports to port

Port algorithms and tests into new narrow analyzer interfaces; do not add
either old repository as a runtime dependency.

### Historical numerical oracle

From `leo-tracker@0bb80d14759fd8496b74e7d3219a690be18565a6`:

- `/home/mouse9911/gits/leo-tracker/src/leo_tracker/radio/beacon/pilots.py`:
  published edge-pilot states/frame, epoch search, symbol tracking,
  conditioned search, and roll control.
- `/home/mouse9911/gits/leo-tracker/src/leo_tracker/radio/beacon/acquisition.py`:
  `pilot_symbolwise_v3`, receiver-centered CFO domains, subband extraction,
  and conditioned refinement.
- `/home/mouse9911/gits/leo-tracker/src/leo_tracker/radio/beacon/decode.py`:
  known-pilot demodulation, residual CFO, QAM metrics, and inverse-noise
  dual-receiver combination.
- `/home/mouse9911/gits/leo-tracker/src/leo_tracker/radio/beacon/analysis.py`,
  `templates.py`, and `structure.py`: the 10 ms / 100 ms replay cadence and
  frame constants.
- `/home/mouse9911/gits/leo-tracker/src/leo_tracker/radio/beacon/lnb_calibration.py`:
  receiver frequency-center semantics. Its mutable-file workflow should not
  be ported; only the numerical meaning belongs in an immutable calibration
  contract.
- `/home/mouse9911/gits/leo-tracker/tests/test_radio_beacon.py`,
  `test_relative_phase.py`, `test_pilot_injection.py`, and
  `test_radio_calibration_applied.py`: waveform, off-grid CFO, control, and
  calibration oracle cases.

### Native Redux parity implementation

From `leo-tracker-redux@b2b8827832715f7cd45196cd08919bcc5dd2a3f0`:

- `/home/mouse9911/gits/leo-tracker-redux/src/leo_flow/analysis/recording/starlink_templates.py`
- `/home/mouse9911/gits/leo-tracker-redux/src/leo_flow/analysis/recording/starlink_acquisition.py`
- `/home/mouse9911/gits/leo-tracker-redux/src/leo_flow/analysis/recording/starlink_pilot_constellation.py`
- `/home/mouse9911/gits/leo-tracker-redux/src/leo_flow/analysis/recording/starlink_symbolwise_replay.py`
- `/home/mouse9911/gits/leo-tracker-redux/src/leo_flow/analysis/recording/starlink_pattern_symmetric_qam.py`
- `/home/mouse9911/gits/leo-tracker-redux/src/leo_flow/analysis/recording/starlink_receiver_agnostic_cfo.py`
- `/home/mouse9911/gits/leo-tracker-redux/src/leo_flow/analysis/recording/starlink_surrogate_null.py`
- `/home/mouse9911/gits/leo-tracker-redux/src/leo_flow/analysis/recording/starlink_full_dwell_response.py`

The highest-value regression/oracle tests are:

- `/home/mouse9911/gits/leo-tracker-redux/tests/recording_analysis/test_starlink_templates.py`
- `/home/mouse9911/gits/leo-tracker-redux/tests/recording_analysis/test_starlink_acquisition_v0_3.py`
- `/home/mouse9911/gits/leo-tracker-redux/tests/recording_analysis/test_starlink_pilot_constellation.py`
- `/home/mouse9911/gits/leo-tracker-redux/tests/recording_analysis/test_retro_qam_external_corpus.py`
- `/home/mouse9911/gits/leo-tracker-redux/tests/recording_analysis/test_starlink_symbolwise_replay.py`
- `/home/mouse9911/gits/leo-tracker-redux/tests/recording_analysis/test_starlink_symbolwise_replay_external.py`
- `/home/mouse9911/gits/leo-tracker-redux/tests/recording_analysis/test_starlink_receiver_agnostic_cfo_raw_iq_v0_6.py`
- `/home/mouse9911/gits/leo-tracker-redux/tests/recording_analysis/test_starlink_full_dwell_response.py`

The existing external tests use `pytest.skip` when QNAP or J1 is absent. The
new protected local corpus lane must instead fail when a `REQUIRED` fixture is
absent, while J1 must appear explicitly as non-executable
`UNAVAILABLE_HISTORICAL_EVIDENCE` rather than skip or pass. Hardware- and
QNAP-marked audits may remain explicit optional lanes, but never silent skips.

### Corpus and synthetic-control machinery

- `/home/mouse9911/gits/leo-tracker-redux/benchmark/qnap_real_dataset.py`
- `/home/mouse9911/gits/leo-tracker-redux/benchmark/manifests/qnap-synchronised-real-development-v1.json`
- `/home/mouse9911/gits/leo-tracker-redux/benchmark/qnap-synchronised-real-development.md`
- `/home/mouse9911/gits/leo-tracker-redux/benchmark/starlink_pilot_if.py`
- `/home/mouse9911/gits/leo-tracker-redux/benchmark/starlink_scan_fixture.py`
- `/home/mouse9911/gits/leo-tracker-redux/benchmark/starlink_detector_matrix.py`

Reuse the explicit truth tiers, safe relative-path validation, digest checks,
paired-RX layout checks, and detector-independent injection generation. Do not
port the old benchmark's broad orchestration or legacy storage model.

### Reports that freeze interpretation

- `/home/mouse9911/gits/leo-tracker-redux/reports/qam_retro_investigation.md`
- `/home/mouse9911/gits/leo-tracker-redux/reports/qam_retro_analysis.py`
- `/home/mouse9911/gits/leo-tracker-redux/reports/starlink_symbolwise_replay_audit.md`
- `/home/mouse9911/gits/leo-tracker-redux/reports/recording_rec_01M09J1R6E59GCC8ANJVYVRN1B_signal_investigation.md`
- `/home/mouse9911/gits/leo-tracker-redux/reports/rec_01M09J1R6E59GCC8ANJVYVRN1B_analysis.py`
- `/home/mouse9911/gits/leo-tracker-redux/docs/starlink-full-dwell-response.md`
- `/home/mouse9911/gits/leo-tracker/reports/starlink-detector-evaluation/REPORT.md`
- `/home/mouse9911/gits/leo-tracker/reports/sync-scan-cross-radio-2026-08-14/REPORT.md`

These reports are interpretation and acceptance references, not executable
runtime dependencies and not proof of calibrated detection.
