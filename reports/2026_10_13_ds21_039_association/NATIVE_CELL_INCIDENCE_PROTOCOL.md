# DS21-039 native-cell incidence gate

This is a training metadata diagnostic, not a position or association fit. It
tests whether the fixed zero-origin OFDM-cell prior's demonstrated boundary
sensitivity is present in the original DS21-039 input inventory. No source-default
model, candidate prior, bank, candidate exclusion or persisted contract changes.
Retain fitted c throughout; no c=0 work is part of this diagnostic.

## Authority and reconstruction cost

Run the new `ds21_039_native_cell_incidence.run(directory, frozen_protocol)` only
after root has reviewed and frozen its source closure and input bindings. The
freeze contains exact `policy=POLICY`, `inputs` (the original root-cause training
handoff), `factorial_freeze`, `factorial_protocol`, `factorial_terminal`,
`factorial_seal`, `factorial_metadata`, `endpoint_arrays`, `source_sha256` and
`snapshot_paths`. Every file binding is an absolute path and SHA256. Sources are
archived locally before execution; source snapshots are not duplicated in Git.
Code-only `sources()` preloads the pinned input adapter. The standalone named
module below is the complete execution recipe and is itself source-bound.

From the authoritative research checkout with its scientific Python environment
and `PYTHONPATH=src:tools`, run these commands separately, each under external
`timeout --signal=TERM --kill-after=5s 40s`:

```text
python -m ds21_039_native_cell_incidence freeze \
  --directory /home/mouse9911/gits/leo-ds21-three-models/reports/2026_10_13_ds21_039_root_cause/local/native-cell-incidence-v1 \
  --factorial-freeze /home/mouse9911/gits/leo-ds21-three-models/reports/2026_10_13_ds21_039_root_cause/local/timing-calibration-factorial-v1/freeze.json \
  --inputs /home/mouse9911/gits/leo-ds21-three-models/reports/2026_10_13_ds21_039_root_cause/inputs-v1.json
python -m ds21_039_native_cell_incidence run \
  --directory /home/mouse9911/gits/leo-ds21-three-models/reports/2026_10_13_ds21_039_root_cause/local/native-cell-incidence-v1
python -m ds21_039_native_cell_incidence read \
  --directory /home/mouse9911/gits/leo-ds21-three-models/reports/2026_10_13_ds21_039_root_cause/local/native-cell-incidence-v1
```

`freeze` performs only metadata authority/source qualification. It calls the
genuine factorial `read_profile_parent` and `read_sealed` ports and validates
historical source subsets, without invoking the old ambient source-closure
equality gate under the newly loaded module. It constructs exact absolute
bindings and the local source archive; the caller supplies no handwritten
replacement parent receipts. `run` alone may reconstruct the permitted training
metadata and writes under `diagnostic/`. `read` refuses a missing final seal and
cannot start an audit. Freeze/read also have a thirty-second internal limit.

The metadata and endpoint NPZ are the completed timing/calibration factorial's
`diagnostic/metadata.json` and `arrays/endpoint-original-all.npz`. Their hashes,
protocol and terminal must appear in the bound parent final seal. The parent
must be complete, fitted-c, reference-free, held-free and optimizer-free. Its
input handoff must be the exact same one used here. Parent live/archive source
bytes are checked as an unchanged subset of the new source authority; the new
runner is an explicit source addition, not a historical source rebinding.

**Saved arrays alone are insufficient.** They retain collapsed candidate IDs and
window rows but omit measured CFOs and native receive times. Reconstruct all
passing alternatives by loading the pinned original TrackingInput, performing
the existing seed-20261012 twenty-second counter partition, and calling scanner
support projection only on its training child. No position-window preparation,
track reconstruction, bank loading, propagation, likelihood, gradient, optimizer,
held candidate projection or reference evaluation is authorized.

Require the original assignment digest, seed, block length, held-block labels
(metadata only), probe counts and raw-capture identity. Require exact original
training window IDs, winner IDs, receive times, receiver/channel/RF, visit and
counter-block metadata. Reuse the unchanged native branch-input helper and require
its collapsed candidate-ID/window-row inventory to equal the sealed endpoint NPZ.
Then retain all passing alternatives in those same original training windows.
Missing support or changed identity is a failed audit, never a substituted row.

The single invocation has a **30-second internal total**, TERM at **40 seconds**,
KILL at **45 seconds**. All loading, partitioning and support projection cost is
included and separately recorded as reconstruction/preparation time; authority
hashing and incidence calculation times are reported too. There is no zero-prep
claim. No competing heavy research process should run during the slice.

## Fixed definition and falsification

For exact native CFO x, canonicalize only to the recorded sampling domain fs.
The current cell is `floor(canonical_fs(x)/A + 0.5)`, with `A=1/4.4e-6` Hz.
Require recorded fs=2.5MHz=11A within 1e-8 Hz. Sampling-circle pair distance is
`abs((x-y+fs/2) % fs - fs/2)`; do not fold this distance modulo A. Adjacent cells
have label difference 1 or 10 modulo 11, preserving adjacency at the sampling seam.

Within each original window, flag pairs only when they occupy adjacent distinct
cells and their sampling-circle distance is **at most 125 Hz**. This threshold
is the original `ds21_joint.objective`'s source-bound `HARD60_SCORE.sigma_hz`, not
a new fitted or tuned choice; execution checks that original constant. Do not
compare candidates across windows, receivers or visits. Unequal native support
times within a window are retained without asserting common emitters.

Persist every window and alternative's exact ID, CFO, time, rank, margin, canonical
CFO, original cell, boundary distance and declared 1/(B*n) prior. Keep original
window receiver/channel/RF, winner and counter-block fields, including missing
block labels. Report candidate and collapsed counts, pair/window incidence,
every flagged pair and its exact sampling-circle distance, and pair counts by
original block. Pair counts and windows are descriptive, not independent trials.

Zero pairs falsifies this narrow close-pair boundary mechanism for this inventory.
Nonzero incidence alone establishes neither a defect nor a meaningful likelihood
effect. It may motivate a separately reviewed fixed-state posterior attribution,
with geography, timing, calibration, bank and original priors held fixed. No
additional evaluation or model change is automatically authorized by this gate.

## Immutable outcomes

An exclusive `started.json` is claimed before input reconstruction. An interrupted
slice without a final seal is unavailable and may not be retried. All ordinary
failures/timeouts retain their stage/error and a terminal failure receipt. A
completed audit writes full native inventory, summary, termination, terminal and
final hash seal. Cached calls validate the immutable control and receipts and
perform no input loading or reconstruction. No failure becomes a zero-incidence
result. No new localization accuracy or held-prediction claim is expected.
