# ALGO08v3 successor on DS30-0374

The successor reproduced the installed ALGO08v3 fix and publication exactly on DS30-0374. It reached the detection file 8.92 s earlier, then finished 4.21 s later overall and used 1.47 s more CPU. The measured end-to-end speedup was 0.975× on this one cold pair. [Direct pair receipt](measurements/successor-DS30-0374-pair.json)

| Measurement | Installed ALGO08v3 | Successor |
| --- | ---: | ---: |
| Run order | Second | First |
| Launch through detections (s) | 54.047 | 45.127 |
| Detections through terminal (s) | 37.626 | 40.476 |
| Terminal through publication and exit (s) | 72.733 | 83.010 |
| Total elapsed (s) | 164.405 | 168.613 |
| Process CPU (s) | 63.587 | 65.061 |
| Input blocks charged | 16,468,456 | 16,468,552 |
| Input pages cached at launch | 217 of 2,054,132 | 217 of 2,054,132 |

Stage clocks use detection and terminal modification times and the measured launch-to-exit duration. Linux `cachestat` observed all 106 compressed members in both arms. The launches were about 395.5 s apart, with about 226.9 s between successor exit and baseline launch. The verification fix and the shared lock queue account for the gap. One-second samples during each publication showed the backing bulk device at approximately 100% utilization. The cache observations and block accounting establish comparable cold launches. The fixed order, lock gap and varying storage load limit attribution of the observed stage differences. [Direct pair receipt](measurements/successor-DS30-0374-pair.json)

All 92 prefetched members were used, totaling 7,299,934,849 compressed bytes, with zero fallbacks. Waiting for the buffers took 1.358 s in aggregate and the worker used 3.025 CPU s. The installed baseline submitted 92 advisory reads of 16 MiB each. The successor used the stock orbit policy for this fix. [Prefetch and guard counters](measurements/successor-DS30-0374-pair.json)

Both runs used the same raw recording, causal archive and region. The full detection and terminal documents matched byte for byte, including the 9,288 ordered probes, 4,157 selections and both calibration-arm fits. Both owner digests, scientific path and grid digests, and all eight PNG file hashes matched. The pair also reproduced the installed ALGO08v3 production smoke witness. [Pair comparison](measurements/successor-DS30-0374-pair.json) · [Production witness](gauss-smoke.json)

Both calibration arms used the same observations, candidates, other priors and search budget. Fitting `c` reduced RF RMS by 0.0161 Hz. Horizontal error against the existing DS30 reference increased by 0.0799 km. [Fit witnesses](measurements/successor-DS30-0374-pair.json) · [DS30 reference scores](first-55/recordings.csv)

| Calibration | RF RMS, both builds (Hz) | Horizontal error, both builds (km) |
| --- | ---: | ---: |
| Fixed zero | 101.5359 | 1.8554 |
| Fitted | 101.5198 | 1.9354 |

## Reproduce the pair

The successor uses installed ALGO08v3 specification `6cdbac1e8496…`, the same native detector and publication stack, and a process-local overlay. Full-member prefetch replaces the 16 MiB advisory read. The orbit guard enters only on the frozen solver's orbit-support retry and uses the exact support code already evaluated on DS30-0022, DS30-0129 and DS30-0239. [Prefetch implementation and fixture results](../single-core-2x/full-member-prefetch.md) · [Saved orbit-support comparisons](../single-core-2x/algo08v3-solver-orbit-support.md)

The benchmark uses the DS30-0374 assignment's sealed segments, causal archive and region for both arms. The successor arm used code commit `90a31fad4` and the baseline arm used the resumed driver at `47454895f`. The normal Gauss recording account ran both arms under the shared Gauss flock on CPU 2 at nice 15, best-effort I/O priority 7 and a single numerical thread. Each arm starts in an empty output directory. The arms share an initially empty Matplotlib configuration directory. Both launchers verify their pins before the timing boundary. Cache observations occur immediately before each arm, with the operating system managing the cache throughout. [Frozen DS30-0374 assignment](../single-core-2x/measurements/DS30-0374-exact-curved-lookahead.json) · [Installed production witness](gauss-smoke.json)

```sh
repo=/var/tmp/leo-algo08v3-next-pair
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
run_output=/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/v3-successor-DS30-0374-replay

sudo -n systemd-run --quiet --wait --pipe --collect \
  -p User=leo -p Group=leo -p Nice=15 -p CPUAffinity=2 \
  -p IOSchedulingClass=best-effort -p IOSchedulingPriority=7 \
  /usr/bin/env PYTHONPATH="$repo:$release/src:$release" \
  "$release/venv/bin/python" -BPs "$repo/reports/ALGO08/v3/triage_successor.py" \
  "$run_output" --first successor
```

The first startup stopped before I/Q acquisition when a research helper import failed against the frozen installation. The corrected launcher verifies and imports the two pinned helpers into the prospective read path at preflight, and restores their module bindings before the verified demand path runs. The startup receipt has zero measured arms. After the successor subsequently completed, the installed runtime's older workspace API stopped the publication verifier. The corrected driver verified the preserved successor files and completed the missing baseline with `--resume` under a newly acquired Gauss lock. [Startup receipt](measurements/successor-DS30-0374-startup-failure.json) · [Partial receipt](measurements/successor-DS30-0374-partial.json)
