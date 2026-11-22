# Nested DS30 single-core qualification

The stage runner uses the first four or first sixteen entries in the frozen DS30 order. Each `run` starts one pair on CPU 2 under the existing low-priority Gauss lock. The first case runs the candidate first, and the first arm alternates by the frozen case rank. An explicit `--case` must match the next unmeasured assignment. The case's own directory retains the pair. A failed, incomplete, stale or development attempt prevents advancing that workspace. [Frozen panel](../ds30-optimized/panel.json) · [Stage runner](ds30_stage.py) · [Paired launcher](../../../tools/pipeline_eval/qualification/paired_publication.py)

The runner checks the locked case binding, physical recording, offer, capture identity and admitted visit counts. It checks the immutable candidate specification, source and native library digests, and the recorded baseline and candidate launchers. A new pair records the assigned archive path and the digest of its snapshot inventory. The receipt binds the same inventory before and after the timed processes. The release verifies the contents of each TLE object it reads. Archive inventory checks remain outside the timed boundary. [Original DS30 input bindings](../../../tools/pipeline_eval/qualification/ds30_full_inputs.py)

`inventory` reopens the actual terminal, detector outputs, grid, path and figures as applicable. It verifies their bindings and exact science across the pair. The lossless renderer also checks the decoded pixels and non-image PNG chunks. The audit digest binds the checked result to the original pair bytes. Withheld results count if both arms reproduce the same reason and evidence. `score` reports the paired-median and summed candidate-to-baseline elapsed ratios only when every assigned pair verifies. Both must be at most 0.50. It then reports fixed-zero and fitted-calibration position errors using the original DS30 reference authority. No additional journal is needed. [Artifact audit](audit_shared_publication.py) · [Timing and quality protocol](PROTOCOL.md)

## Read-only check of the existing lead case

The saved DS30-0374 batch pair verified the original raw authority, candidate and baseline pins, both calibrated endpoints and owner maps, grid and path, all 9,288 detector rows and all eight PNGs. It used the live archive `/var/lib/leo/tle` with capture-time cutoffs. Its legacy pair receipt omits the archive argument. The terminal and publication record an orbit policy, but the saved detector, terminal, manifest and sidecar bindings do not name a selected TLE object inventory. The outputs therefore establish raw, regional and scientific equality without establishing equivalence to the frozen per-case archive. The lead remains a development measurement. The other three assignments are missing, and both elapsed gates remain unreported. The check did not launch a benchmark. [Read-only stage result](measurements/ds30-stage-read-only.json) · [Lead measurement](batch-publication.md)

Fifty-eight component tests passed, covering read-only storage, qualification with synthetic withheld receipts, one-case pacing, missing or swapped assignments, interrupted-stage recovery, archive changes and decoded PNG integrity. [Storage tests](../../../tests/storage/test_fast_scan.py) · [Stage tests](../../../tests/pipeline_eval/test_ds30_stage.py)

## Commands

From the checkout root, choose the frozen build and a local workspace writable by the inference account. The command below uses the same candidate pins as the saved read-only check. `run` preserves the output in the assigned canonical case directory. Later calls use the same workspace and build. Escalating from four to sixteen requires an explicit `--size 16` after review.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
build=/tmp/leo-algo08v2-2x-bench/integration-batch-orbit
workspace=/tmp/ds30-v2-stage-e40942
spec_digest=e40942b4f8ef6581b14c2ad7d49baf73c2519afa17a00f78339c92b7731cbb6a

stage() {
  action=$1
  shift
  sudo -n -u leo -- env PYTHONPATH="$PWD:$PWD/src:$release" \
    "$release/venv/bin/python" -B -m reports.ALGO08.single-core-2x.ds30_stage \
    "$action" "$workspace" "$build/reports/ALGO08/single-core-2x/run-candidate" \
    "$build/spec.json" "$spec_digest" "$@"
}

stage inventory --size 4
stage run --size 4 --case DS30-0374
stage score --size 4
```

To reproduce the historical read-only check, point `workspace` at a separate view that contains a `DS30-0374` symlink to `/tmp/leo-algo08v2-2x-bench/physical-endpoint-paired/DS30-0374-batch`, then run `stage score --size 4` only. Use a new qualification workspace for timed cases.

## Recovering an interrupted stage

Keep the original workspace and report its `inventory` result, including the failed or incomplete assignment. For a subsequent attempt with the same frozen build and inputs, set `workspace` to a new directory. Link the original case directories for the contiguous verified prefix into that directory under their same DS30 IDs. `inventory` rechecks those receipts and `run` resumes at the first missing assignment in the original order. This preserves any completed timings and the failed attempt. Record the original and new workspace paths with the recovery reason. For a changed build or input, start at rank one in a new workspace.
