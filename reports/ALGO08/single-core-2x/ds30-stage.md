# Nested DS30 single-core qualification

The stage runner uses the first four or first sixteen entries in the frozen DS30 order. Each `run` starts one pair on CPU 2 under the existing low-priority Gauss lock. The first case runs the candidate first, and the first arm alternates by the frozen case rank. An explicit `--case` must match the next unmeasured assignment. The case's own directory retains the pair. A failed, incomplete, stale or development attempt prevents advancing that workspace. [Frozen panel](../ds30-optimized/panel.json) · [Stage runner](ds30_stage.py) · [Paired launcher](../../../tools/pipeline_eval/qualification/paired_publication.py)

The runner checks the locked case binding, physical recording, offer, capture identity and admitted visit counts. It checks the immutable candidate specification, source and native library digests, and the recorded baseline and candidate launchers. A new pair records the assigned archive path and the digest of its snapshot inventory. The receipt binds the same inventory before and after the timed processes. The release verifies the contents of each TLE object it reads. Archive inventory checks remain outside the timed boundary. [Original DS30 input bindings](../../../tools/pipeline_eval/qualification/ds30_full_inputs.py)

`inventory` reopens the actual terminal, detector outputs, grid, path and figures as applicable. For exact candidates it verifies identical science across the pair. The exact lossless renderer audit also checks the decoded pixels and non-image PNG chunks. Withheld results count if both builds reproduce the same reason and evidence. The audit digest binds the checked result to the original pair bytes. `score` reports the paired-median and summed candidate-to-baseline elapsed ratios only when every assigned pair verifies. Both must be at most 0.50. It then reports fixed-zero and fitted-calibration position errors using the original DS30 reference authority. [Artifact audit](audit_shared_publication.py) · [Timing and quality protocol](PROTOCOL.md)

## Frozen conditional-residual candidate

The runner selects approximate comparison only for the reviewed conditional-residual specification at canonical SHA-256 `65b664d49a5e91baf1fb593c19808f4cf32921d0c17ffe6145d61189570089c6`. Inventory verifies the same assigned raw authority, region, causal archive, builds and timing boundary. It independently checks each detector against its terminal and each terminal against the standard publication, including both calibration endpoints, grid and path when fixed, and all eight expected decodable PNGs. It records differences in selections, owners, path, grid, decoded figures and terminal decisions. Valid differences count toward completion. [Publication comparison](compare_publications.py) · [Frozen receiver and development results](receiver-residual-prefix-192.md#complete-physical-and-simulated-publications)

At full coverage, the score reports matched and unmatched fixes, error for every assignment, and returned-error P50 and P90 at each historical reference site in both calibration arms. Quality requires retaining every baseline fix on containing offers and avoiding worse P50 or P90 at each site. It counts newly issued fixes separately. Both the elapsed and quality results are reported if either gate fails. DS30 is a single physical development site, and the stage always reports `geographic_confirmation: false`.

The read-only check verified both saved DS30-0016 run orders against the frozen DS30 input and causal archive. Each retained 439 selections and lost one. Owners, both fixes, grid and path matched. The changed pixels were in the channel 5–8 `all`, `residuals` and `unassociated` figures. The public northern development pair passed the artifact check with all 456 selections, both fixes and all eight rendered figures matching. These saved pairs are outside the nested DS30 stage. A separate empty stage reported all four assignments missing and left the speed and quality gates unset. No benchmark was launched for these checks. [Read-only receipts](measurements/ds30-conditional-stage-read-only.json)

Sixty-eight component tests passed. The synthetic conditional stage advanced after a valid lost fix, rejected tampered evidence and reported both failed gates when the complete stage was slower and less accurate. [Stage tests](../../../tests/pipeline_eval/test_ds30_stage.py)

## Read-only check of the existing lead case

The saved DS30-0374 batch pair verified the original raw authority, candidate and baseline pins, both calibrated endpoints and owner maps, grid and path, all 9,288 detector rows and all eight PNGs. It used the live archive `/var/lib/leo/tle` with capture-time cutoffs. Its legacy pair receipt omits the archive argument. The terminal and publication record an orbit policy, but the saved detector, terminal, manifest and sidecar bindings do not name a selected TLE object inventory. The outputs therefore establish raw, regional and scientific equality without establishing equivalence to the frozen per-case archive. The lead remains a development measurement. The other three assignments are missing, and both elapsed gates remain unreported. The check did not launch a benchmark. [Read-only stage result](measurements/ds30-stage-read-only.json) · [Lead measurement](batch-publication.md)

Fifty-eight component tests passed, covering read-only storage, qualification with synthetic withheld receipts, one-case pacing, missing or swapped assignments, interrupted-stage recovery, archive changes and decoded PNG integrity. [Storage tests](../../../tests/storage/test_fast_scan.py) · [Stage tests](../../../tests/pipeline_eval/test_ds30_stage.py)

## Commands

The score's `observed_timing` includes median paired and summed candidate/deployed ratios for elapsed and CPU time. It lists the contributing case IDs twice, once for all verified pairs and once for pairs where both runs explicitly reported zero filesystem input blocks. Older receipts without those counters contribute only to the all-pairs group. These diagnostics are available during triage. The formal elapsed and position gates are still computed only at complete stage coverage.

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

For an authorized pair where cache state matters, add `--cache-library` to `stage run`.
The runner checks the current sealed manifest roster against that case's frozen binding and
queries only its compressed members. Each observation runs under the same Gauss lock immediately
before the arm's CPU, elapsed and stage clocks. The pair receipt and its inventory entry record
`cache_observation.arms` and the manifest pins. An unavailable query is counted by error, including
`ENOSYS` for a missing syscall and `EPERM` or `EACCES` for denied access. When none of the members
can be queried, `cached_pages` is null. The observation reads manifest headers and opens payload
descriptors without reading payload data or issuing cache hints. [Storage accounting](storage-io-accounting.md)

```sh
cc -O2 -shared -fPIC tools/pipeline_eval/qualification/cache_residency.c \
  -o /tmp/leo-algo08v2-2x-bench/ds30-cache-residency.so
stage run --size 4 --case DS30-0374 \
  --cache-library /tmp/leo-algo08v2-2x-bench/ds30-cache-residency.so
```

For the conditional-residual build, use the same function with these settings and a separate workspace.

```sh
build=/tmp/leo-algo08v2-2x-bench/integration-conditional-residual-reviewed
workspace=/tmp/ds30-v2-stage-65b664
spec_digest=65b664d49a5e91baf1fb593c19808f4cf32921d0c17ffe6145d61189570089c6
stage inventory --size 4
stage run --size 4 --case DS30-0374
stage score --size 4
```

To reproduce the historical read-only check, point `workspace` at a separate view that contains a `DS30-0374` symlink to `/tmp/leo-algo08v2-2x-bench/physical-endpoint-paired/DS30-0374-batch`, then run `stage score --size 4` only. Use a new qualification workspace for timed cases.

## Recovering an interrupted stage

Keep the original workspace and report its `inventory` result, including the failed or incomplete assignment. For a subsequent attempt with the same frozen build and inputs, set `workspace` to a new directory. Link the original case directories for the contiguous verified prefix into that directory under their same DS30 IDs. `inventory` rechecks those receipts and `run` resumes at the first missing assignment in the original order. This preserves any completed timings and the failed attempt. Record the original and new workspace paths with the recovery reason. For a changed build or input, start at rank one in a new workspace.
