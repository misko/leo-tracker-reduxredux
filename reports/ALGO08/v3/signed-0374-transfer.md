# DS30-0374 saved publication transfer

The signed-enabled joint route published a complete DS30-0374 result in **19.129 s**, compared with **24.134 s** for installed v3, a **1.26×** speedup from the saved detector handoff through standard publication. Its phase-history guard declined the signed endpoint adjustment. The ordinary joint finish produced the returned coordinates. The candidate passed the prespecified per-arm transfer tolerance, with 4.2 m more horizontal error for (c=0) and 6.7 m less for fitted (c). This result covers one physical prefix. [Frozen protocol](signed-0374-transfer-protocol.md) · [Measurement receipt](measurements/signed-DS30-0374-publication.json)

| Saved publication measure | Installed v3 | Signed-enabled joint |
|---|---:|---:|
| Solve and numerical grid elapsed (s) | 21.451 | 16.624 |
| Solve and numerical grid CPU (s) | 21.383 | 16.620 |
| Publication elapsed (s) | 24.134 | 19.129 |
| Publication CPU (s) | 24.035 | 19.099 |
| Numerical grid points | 179 | 179 |
| Standard PNGs | 8 | 8 |

The candidate spent 10.391 CPU s before qualification and evidence, including cold discovery (5.187 s), initial gating (1.232 s), salvage (2.112 s), predictive support (1.374 s) and joint finish (0.486 s). The signed phase-history test cost 0.048 CPU s. Its future and disjoint-future gains were −6.645 and −11.772, so it kept the ordinary endpoint. Standard numerical evidence cost 3.351 CPU s. Those instrumentation scopes sit inside the measured solver budget. Both solvers had zero objective replay discrepancy in each arm. The candidate required zero full v3 fallback calls.

| Measurement | Calibration arm | Installed v3 | Signed-enabled joint | Candidate minus stock |
|---|---|---:|---:|---:|
| Horizontal error (km) | \(c=0\) | 1.855441 | 1.859620 | +0.004178 |
| Horizontal error (km) | fitted \(c\) | 1.935370 | 1.928706 | −0.006664 |
| RF RMS (Hz) | \(c=0\) | 101.535913 | 101.577325 | +0.041412 |
| RF RMS (Hz) | fitted \(c\) | 101.519803 | 101.594246 | +0.074443 |

Fitting (c) increased the stock horizontal error by 79.9 m while decreasing RF RMS by 0.016 Hz. It increased the candidate horizontal error by 69.1 m and raised RF RMS by 0.017 Hz. Both candidate arms retained all 411 predictive observations and 2,411 of 2,494 conditionally associated observations. Every retained observation had the same satellite owner and role as in stock.

Both runs used the same archived detector packet for 6,770 windows, the supplied 25 km offer, the capture-era TLE archive, and one low-priority CPU 2 core with one numerical thread. The fresh stock output matched the archived v3 raw authority, terminal, calibration arms, observation owner digests, and scientific path and grid digests. All eight stock PNGs matched the archive byte for byte and after RGBA decoding. Both publications wrote eight PNGs, and the audit decoded all sixteen. The linked position figures are the actual encoded outputs. [Stock position PNG](development/signed-0374-stock-position.png) · [Candidate position PNG](development/signed-0374-candidate-position.png)

The first archive verification inadvertently compared the grid digest that includes elapsed time in the decoded-image check. After correcting that check to compare all eight decoded images and the scientific grid digest separately, the pair reused the sealed stock run and ran the signed-enabled route once. The stock process-launch and audit clock was lost at that interruption. Its saved-publication clock and all scientific evidence survived, and the table compares the same publication boundaries for both modes. The pair was sealed before reading the physical reference. The elapsed result begins at the saved detector handoff and supports only a single-case development transfer claim.

## Reproduce

Run from the repository root with read access to the pinned release, archived inputs, and the eligible reference catalogue. `out` should be a new path under a directory writable by the account running the commands. The run and score subcommands separate publication from the reference lookup.

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
runner=reports/ALGO08/v3/signed_0374_transfer.py
out=/var/tmp/signed-0374-repeat
gauss() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
    ionice -c2 -n7 nice -n15 taskset -c 2 timeout 300s \
    env PYTHONPATH="$PWD:$PWD/src" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 "$@"
}
gauss "$release/venv/bin/python" "$runner" run "$out"
gauss "$release/venv/bin/python" "$runner" score "$out" "$out/scored.json"
```
