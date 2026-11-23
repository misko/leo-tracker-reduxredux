# Receiver-first bootstrap on an authenticated empty recording

The 18-visit DS30-0227 raw replay fell from **1.331912 s to 0.498100 s** through fresh process exit, a 2.674× speedup. CPU fell from 1.327260 s to 0.496603 s. The original cancellation receiver emitted 28 admitted probes and zero selected signed factors. The same four visits failed sample support. The sealed detector packet, signed inventory, scan report, withheld publication and stdout receipt matched named ALGO08v3 byte for byte. Both calibration arms withheld their position with `no_active_curvature`. [Paired receipt](empty-bootstrap-results.json)

| Replay | Named v3 or installed control CPU | Receiver-first CPU | Named v3 or installed control elapsed | Receiver-first elapsed |
| --- | ---: | ---: | ---: | ---: |
| DS30-0227 warm original raw | 1.327260 s | 0.496603 s | 1.331912 s | 0.498100 s |
| DS30-0016 original saved packet | 6.008711 s | 6.012506 s | 6.010798 s | 6.017989 s |

Both raw processes launched with all 5,090 compressed recording pages resident. Named v3 incurred 144 filesystem input blocks and three major faults across the full process, while the prototype incurred zero. Both outputs landed on fresh tmpfs directories. One raw pair and one saved pair were run in stock-first order. The raw clock includes interpreter startup, source and asset checks, complete signed acquisition, immutable publication, stdout and process exit. The stock launcher additionally writes its release marker. The prototype writes its own research source and handoff audit.

## Execution boundary

Named v3 already defers seven package reexport facades, a measured 0.58–0.67 s import and setup improvement in the earlier bounded trial. Earlier private checked-hash bytecode shaved 0.071 s CPU across the frozen build's actual first-party misses. The new mode keeps the installed lazy facades and postpones the separate solver, renderer and their transitive imports until the acquisition warrants them. On the empty replay, SciPy, the position solver and Matplotlib were absent through exit. [Lazy facade study](../single-core-2x/receiver-startup.md) · [Checked bytecode study](../single-core-2x/receiver-bytecode-startup.md)

The prototype runs the named launcher's frozen specification checks, verifies the additional used sources and loads reviewed installed scanner and native detector definitions. It keeps the original signed window and member verification, compressed member lookahead, paired SHA and causal continuation. The empty guard requires every authenticated probe's selected-candidate array to be empty and preserves installed frequency-input validation for those probes. The normal installed scanner seals the acquisition, publishes the inventory and emits the same withheld files. Pinned numerical assets are checked as files without loading their unused numerical provider. Any selected factor triggers the full installed fit and rendering path in the same process. The handoff binds the prior packet to the requested inventory and permits exactly one publication call. [Frozen protocol](empty-bootstrap-protocol.md) · [Research implementation](empty_bootstrap.py)

The prototype spent 1.2 ms CPU on installed source checks, 259.3 ms on receiver setup, 1.9 ms on receiver asset checks, 126.4 ms on authentication and acquisition, and 10.4 ms on the empty decision and publication. Those in-process timers start after executable imports and end before the separate audit write. The external charge was 496.6 ms CPU.

## Active data and scope

The saved DS30-0016 packet has 1,426 probes and 440 selected signed factors. Both arms and both executions used 109 associated points with identical owner digests. The `c = 0` solution was 37.83493818°, −122.49130097° with RF RMS 109.375 Hz. The fitted-`c` solution was 37.83568176°, −122.49419045° with RF RMS 109.479 Hz. The decision, raw authority, scientific grid and path, all eight encoded PNGs and all eight decoded RGBA arrays matched. Both exercised fresh solver and rendering setup, with zero waveform acquisitions. The 7 ms elapsed increase in this one saved pair prices the observed fallback, whose raw active latency remains unmeasured.

The result applies to fully resident, authenticated, zero-factor playback on DS30-0227. A published withheld outcome can also arise from nonempty input, and those acquisitions take the original numerical route. The experimental import boundary is tied to the exact reviewed source hashes. Cold storage, rates of empty evidence across recordings and population-wide timing remain open.

## Reproduce

Run from this isolated worktree against the installed release, one Gauss slot at a time. The warm-up in the driver prepares the private font cache, and recording page residency is checked at each raw launch. The timing process records external resource use and validates the original archived DS30-0227 assignment and installed receiver identity.

```bash
trial=$(mktemp -d /dev/shm/leo-empty-bootstrap.XXXXXXXX)
sudo -n chown leo:leo "$trial"
sudo -n chmod 755 "$trial"
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock sudo -n -u leo \
  ionice -c2 -n7 nice -n15 taskset -c 2 env \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD/src:$PWD:$payload:$release/src:$release" \
  "$release/venv/bin/python" -BPs reports/ALGO08/v3/empty_bootstrap_trial.py "$trial/trial"
```

Four new component tests and six existing lazy-startup tests passed under the same resource policy. An untimed empty saved handoff preflight used the previously sealed named-v3 detector packet with no waveform access. [Component tests](../../../tests/pipeline_eval/test_empty_bootstrap.py)
