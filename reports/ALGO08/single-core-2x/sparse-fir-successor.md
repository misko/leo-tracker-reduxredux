# Frozen sparse-ranking and tiled-FIR successor

The research launcher is `/tmp/leo-algo08v2-2x-bench/integration-ad417-sparse-fir/reports/ALGO08/single-core-2x/run-candidate`. Its canonical specification is `sha256:cc63459af6fb2c748c04fd0ea6810a5044ce77ef7c8286424717cddbfd6916a1`. It combines the measured sparse rank projection and reviewed tiled FIR build `cb57aa1e83463ccb7fe491115f961bb21f565736838eee110d7b398a974f1898` with the exact `ad417aaa5` parent. The freeze inherits 1,765 files byte for byte, including the original regional guard, screened tiled finish, Graph, posterior grid, ingress, rendering and startup. The only changed or added files are the specification, research entry, sparse projector, detector and detector source. The specification rebases the six library paths to the child bundle and retains their digests. [Freeze receipt](measurements/sparse-fir-freeze.json) · [Parent freeze](measurements/restored-scout-graph-freeze.json)

The launcher checks the actual frozen detector and discovery source bytes, and checks the imported solver, rank and endpoint modules resolve inside the bundle. The sparse wrapper checks the source digest of the loaded released scan implementation and the actual bound shift method. It is active only during discovery ranking, alongside the same association cache as the parent. No wider observation blocks are enabled. [Projection experiment](sparse-rank-projection.md) · [FIR experiment](receiver-fir-tile.md)

## Saved solver comparisons

Both complete solves returned the same decision and reason, both calibration arms, owner hashes, associated point counts and orbit policy. The entire position path and grid and the objective replay matched by canonical digest, with timing and binding fields excluded. DS30-0008 used the exact physical detections, offer and causal archive from the public `ad417aaa5` profile. India used the same simulated waveform, offset offer and causal archive as the archived `e279026b` saved comparison. The parent and that earlier bundle have byte-identical solver tool trees and identical solver configuration. [Saved solve receipt](measurements/sparse-fir-saved.json) · [Physical profile](measurements/restored-scout-0008-solver-profile.json) · [India input provenance](covariance-geographic-transfer.md)

| Saved input | Associated points per arm | RF RMS Hz, fixed zero / fitted | Candidate solver CPU s | Shift calls / fallbacks |
|---|---:|---:|---:|---:|
| DS30-0008, physical | 4,472 | 129.703040 / 129.662931 | 55.091 | 16 / 0 |
| India, simulated | 517 | 15.536351 / 15.305842 | 5.817 | 16 / 0 |

The candidate created no dense projected catalogue copies on either solve. Its dense run avoided 2.31 GB of cumulative full-matrix copy traffic. The historical dense control was profiled, and the historical India control came from a separate measurement. The table records candidate CPU costs without using either historical control to estimate integrated speedup. Both solves entered at saved detections.

## Receiver comparisons

The integrated detector reproduced all scout fields and all six fields of the five exported factors on the three previously divergent DS30-0008 refinement lanes. Direct comparison matched both the archived full-restoration and wrapped-reference builds. The primary integer epoch, fractional epoch and CFO also matched deployment. The loader verified the paired detection authority, binding, segment and decoded I/Q digests, lane, channel, sample counter and RF center for each visited lane. [Integrated receiver receipt](measurements/sparse-fir-receiver.json) · [Archived reference factors](measurements/receiver-cfo-wrap-trace.json.gz)

| Archived visit | Receiver | Channel | Exactly matched factors |
|---|---:|---:|---:|
| 2661 | 1 | 6 | 2 |
| 3298 | 0 | 3 | 2 |
| 3869 | 0 | 6 | 1 |

The existing Austin experiment exercised the identical detector SHA on four physical and four null calls, with every factor equal to the wrapped reference. No additional Austin calls or raw panels ran. The integrated checks establish arithmetic parity on the exercised paths. They do not measure full-recording throughput, rendering parity, or performance at the boundary of a missing region. [Austin and FIR build receipt](measurements/receiver-fir-tile.json)

## Reproduce

Run from the worktree on Gauss with the archived parent and standalone FIR build present. The freeze refuses to replace an existing directory or receipt. Use the historical bundle path to reproduce its exact digest because the specification includes absolute library paths.

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
bench=/tmp/leo-algo08v2-2x-bench
bundle="$bench/integration-ad417-sparse-fir"
module=reports.ALGO08.single-core-2x.sparse_fir_successor
export PYTHONPATH="$PWD/src:$PWD:$release/src:$release"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
python="$release/venv/bin/python"
"$python" -BPs -m "$module" freeze "$bench" "$bundle" "$bench/sparse-fir-freeze.json"
flock -w 360 "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 \
  "$python" -BPs -m "$module" solve "$bench" "$bundle" \
  "$bench/sparse-fir-freeze.json" "$bench/sparse-fir-saved.json"
binding=/srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0008.json
receiver_receipt_dir=$(sudo -n -u leo mktemp -d /tmp/sparse-fir-lanes.XXXXXXXX)
flock -w 360 "$bench/gauss.lock" sudo -n -u leo nice -n 15 ionice -c2 -n7 taskset -c 2 \
  env PYTHONPATH="$PYTHONPATH" OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  "$python" -BPs -m "$module" receiver "$bench" "$bundle" "$bench/sparse-fir-freeze.json" \
  "$receiver_receipt_dir/receipt.json" --binding "$binding"
sudo -n -u leo cat "$receiver_receipt_dir/receipt.json" > "$bench/sparse-fir-receiver.json"
```

The receiver invocation runs as the service account for read access to the archived physical recording. It reads only the three selected windows, with a 64-window bound on the decoded prefix of any selected compressed chunk. The component tests exercise projection arithmetic and source pin enforcement, tiled FIR arithmetic and the research launcher. All 25 passed. [Reproduction driver](sparse_fir_successor.py) · [Projection tests](../../../tests/pipeline_eval/test_algo08_sparse_rank_projection.py)
