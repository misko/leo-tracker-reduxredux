# Import-only parent for two independent saved fixes

Reusing checked imports in a single-core fork parent saved **0.188 s** with DS30-0016 first and **0.597 s** with North first across two complete saved requests. The first publication completed later in both orders once parent initialization was charged. The second completed sooner after dispatch. The warm parent held about **167 MiB RSS** and **148 MiB proportional resident memory** between requests. [Frozen protocol](preloaded-saved-worker-protocol.md) · [Timing and scientific receipts](measurements/preloaded-saved-worker.json.gz)

| Request order | Fresh sequence wall / CPU, s | Preloaded sequence wall / CPU, s | Wall saving | First child exit from sequence start, fresh / preloaded, s | Second child dispatch-to-exit, fresh / preloaded, s |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS30-0016 → North | 10.110 / 10.107 | 9.921 / 9.919 | 1.86% | 4.434 / 4.732 | 5.670 / 4.994 |
| North → DS30-0016 | 10.587 / 10.584 | 9.989 / 9.984 | 5.64% | 5.974 / 6.085 | 4.605 / 3.682 |

First-child dispatch-to-exit was 4.413→3.754 s for DS30-0016 and 5.954→5.113 s for North. Preloading added 0.951–0.957 s before dispatch, and the interval from second child exit through external parent exit was 0.193–0.220 s. All of it is charged in the sequence totals. Every process completed without major faults or filesystem input blocks on the staged workload. Each sequence started from a new font cache directory, and both modes allowed the second request in that sequence to reuse the disk font cache. The few measured timings describe these exact orders and inputs.

| Order and mode | Idle parent RSS / PSS, MiB | First child peak RSS, MiB | Second child peak RSS, MiB |
| --- | ---: | ---: | ---: |
| DS30-0016 first, fresh | 17.6 / 9.0 | 597.3 | 578.8 |
| DS30-0016 first, preloaded | 167.2 / 147.8 | 539.9 | 603.3 |
| North first, fresh | 17.5 / 9.0 | 632.6 | 598.1 |
| North first, preloaded | 167.1 / 147.7 | 580.7 | 568.5 |

Parent footprints are sampled after initialization. They change by less than 0.2 MiB between requests. Child peaks are per-process high-water marks from `wait4`. Parent and child share copy-on-write memory, so the measurements do not give simultaneous aggregate memory.

## Independent request evidence

The physical DS30-0016 packet is the saved complete unfiltered continuation projection with 475 factors. The North simulation packet is the measured complete guarded history branch with 456. Each child authenticates its own detector, original metadata-only inventory, offer and causal archive, and executes the current graph, signed named finish and standard eight-image publication. The parent’s idle state contains verified release modules, the original scanner and position modules and Matplotlib. It starts each child from the same code-only state on a single thread. All work with positions, owners, request paths, orbit tables and figures takes place inside a child, which exits normally. A component test writes fake coordinates, a native path and orbital state into the first child and confirms their absence in the second. No waveform call ran.

All eight publications reproduced their respective fresh controls. DS30-0016 had 116 ordered owner/role rows in each calibration arm and a 179-point grid. North had 304 per arm and a 137-point grid. Both named finishes were accepted. The authenticated input, terminal, both `c=0` and fitted-`c` coordinates and RF residuals, complete numerical path and grid, and eight genuine PNG file and decoded checksums matched exactly. All sidecars bound each request’s own terminal, input, owner and position image hashes. There was no timing or scientific evidence from a third request, another region, or waveform acquisition.

Earlier work measured first-load cost reductions in independent fresh processes and parsed orbit preparation separately. This experiment reuses checked imports during one bounded batch and rebuilds mutable scientific state in each child. [Fresh active import deferral](active-imports.md) · [Fresh portable orbit index](historical-orbit-index.md)

## Reproduction

Timed source `2dbf3c739`. A post-exit verifier correction finds the saved terminal by publication ID instead of native workspace ID, and parses the original North offer’s implicit screen centre through the release contract. The timed output and process measurements were preserved. Fifteen focused tests passed. Launch as the stage owner from this checkout with its installed release environment and a fresh tmpfs output root.

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
output=/dev/shm/leo-v3-forked-saved-reproduction
run_locked() {
  flock -w 60 -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    sudo -n -u leo ionice -c2 -n7 nice -n15 taskset -c 2 env TMPDIR=/dev/shm \
    OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH="$PYTHONPATH" \
    "$release/venv/bin/python" -Bsm "$@"
}
PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release:$PWD"
run_locked reports.ALGO08.v3.preloaded_saved_worker run "$output"
PYTHONPATH="$PWD/src:$PYTHONPATH"
run_locked reports.ALGO08.v3.preloaded_saved_score "$output"
```
