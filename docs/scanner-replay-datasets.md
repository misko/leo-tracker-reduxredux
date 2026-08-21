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
