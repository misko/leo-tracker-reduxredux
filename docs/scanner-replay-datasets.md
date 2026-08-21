# Scanner replay datasets

Scanner replay datasets splice verified fixed-tuning recording slices into synthetic scanner
sweeps. Absolute time is intentionally discarded. Every dwell remains an independent frame whose
target and source coordinates are authoritative.

## Persisted layout

```text
scanner-replays/<dataset-id>/
  manifest.json
  recipe.v1.json
  truth.v1.json
  <split>/<sweep-id>/
    manifest.json
    iq.ci16.zst
```

Each sweep payload uses the same physical representation as scanner recordings from PR #5:
little-endian CI16 in `(sample, receiver, I/Q)` order, Zstandard compression, contiguous frame
storage coordinates, and per-frame plus whole-payload SHA-256 digests. Frame boundaries, rather
than concatenated sample time, define the individual dwells.

Replay manifests do not claim live radio timing. Each frame instead records the immutable source
recording URI and manifest digest, stream and radio identity, original sample range, receiver set,
and applied radio settings.

Reference labels are stored only in `truth.v1.json`, outside every sweep bundle. Scanner evaluation
should receive a sweep URI and write an ordinary scanner report; scoring joins that report with the
truth file afterward. GLRT-derived labels should be described as reference or silver labels unless
they have independent validation, and uncertain evidence should use `ambiguous`.

## Materialization

Construct a `ScannerReplayDatasetRecipeV1`, then resolve it through the read-only recording adapter
and publish the prepared dataset:

```python
from leo.scanner import prepare_scanner_replay_dataset
from leo.storage import RecordingScannerReplaySource, RecordingStore, ScannerReplayStore

recordings = RecordingStore.open_read_only(recording_root)
source = RecordingScannerReplaySource(recordings)
prepared = prepare_scanner_replay_dataset(recipe, source)
published = ScannerReplayStore(output_root).publish(prepared)
```

Preparation verifies source manifest digests while reading each native CI16 slice. Publication is
atomic at the dataset-directory boundary and never writes beneath `/mnt/qnap01`. A source recording
session may appear in only one dataset split, preventing slices from the same session leaking across
training, validation, and test cohorts.

## Recent-corpus scenario builder

`tools/build_scanner_replay_dataset.py` builds deterministic scenario datasets from the latest
verified standard-radio reports in a bounded recording window. It supports all-active, all-quiet,
and single-active scenarios. Every sweep always contains all eight channel edges in scanner order;
the scenario changes only which source slice and reference label each frame receives.

An active slice is centered inside the longest final trajectory that can contain one dwell. A quiet
slice comes from the largest gap outside all final-trajectory intervals, after expanding every
activity interval by a 200 ms guard on each side. These are silver labels derived from the standard
radio analysis, not independently decoded ground truth. The builder deterministically assigns whole
source sessions to one split before selecting frames, and refuses to build a requested scenario when
there is insufficient split-safe evidence.

For example, an all-quiet dataset and a dataset with only channel 2 upper active can be built with:

```console
tools/build_scanner_replay_dataset.py --dataset-id example-quiet --scenario all-quiet
tools/build_scanner_replay_dataset.py --dataset-id example-ch2-upper \
  --scenario single-active --active-channel 2 --active-edge upper
```

## Standard scanner evaluation

`tools/evaluate_scanner_replay_dataset.py` verifies and reads each replay sweep, reconstructs the
integer-valued complex64 array supplied by the live radio adapter, and calls
`leo.scanner.analyze_scan_sweep` unchanged. It atomically publishes each ordinary `ScannerReport`
alongside a joined truth summary outside the immutable replay dataset. Reported aggregate counts are
frame observations; when separately built scenario datasets reuse a source slice, also inspect the
source coordinates before treating repeated errors as independent observations.

## Segmented Standard scan analysis

`tools/run_standard_scanner_analysis.py` processes each concatenated replay sweep with
`standard-scan-analysis-stitched-v2`. Concatenation remains a storage coordinate only: the analyzer slices
the verified payload at manifest frame boundaries, resets waterfall FFT state at every retune, and
evaluates the complete scanner GLRT64 probe schedule independently inside each dwell. Live scanner
bundles and replay sweeps adapt to the same `SegmentedScannerSource` contract.

Each create-only analysis bundle contains the ordinary scanner report, full numerical metrics, a
scan-wide waterfall with one lane per receiver, and a scan-wide GLRT64 response plot. Both use the
stitched storage-time coordinate. Following the Standard waterfall convention, time increases down
the waterfall and retunes are red horizontal lines; the GLRT uses time horizontally and therefore
marks retunes with red vertical lines:

```text
scanner-analysis/<scan-id>/<analysis-id>/
  manifest.json
  scanner-report.v1.json
  scanner-metrics.v1.json
  presentation/scanner-waterfall.v1.png
  presentation/scanner-glrt64-response.v1.png
```

The full response computation retains the legacy decision point and report `best_margin`; later
probes are retained under a separately named full-response maximum and cannot revise the live
decision after the fact.

Successful interactive and scheduled live scans enter this pipeline immediately after their IQ
bundle is durably published. An all-failed scan has no IQ bundle and retains the existing
inconclusive report fallback. Scheduled acquisition also reconciles every persisted scanner IQ
bundle at startup, creating missing Standard-v2 products after an interrupted or failed earlier
analysis without recapturing RF data. Existing products are digest-verified and reused, so the
repair pass is idempotent. Replay processing uses the same analyzer and renderers through the
read-only replay adapter.

The Scanner tab reads these immutable bundles through `/api/v1/scanner/analyses`. Its left-hand
table selects the newest published analysis variant for each scan; the central pane loads the
persisted waterfall and GLRT64 PNGs without browser-side re-rendering. PNG responses are served only
after their manifest digest has been verified and use immutable private-cache headers.
