# Matched private lookahead buffers on the exact DS30-0049 original prefix

Use the first six original complete members from the independently authenticated DS30-0049 factorial stage. The retained source is `/tmp/leo-v3-ds30-0049-complete-idle01`, on tmpfs, with original manifest `sha256:f73bcb8039b47bed2145436c25cb3241f53cc9bea9b7e528ac00ad90c660812c`, stage receipt `132a92c06c4e126023621027ae6a59ece97612f13715e9c9dc307a46e2ba8ba0`, and factorial seal `78072f6a27b4ce278f517179d87823fc819210fa40655bb3217e9362cf973d95`. The 13 input files include the unchanged original manifest and the six exact indexes and compressed payloads. Require complete residency before and after every child. Member seven and all other capture and causal files are outside the authorized scope. Use existing custody only, with no waveform copy, backing file opens, catalogue query, conditioning or source variants. [Original signed factorial](ds30-0049-receiver-factorial-protocol.md)

Run fresh isolated `d9a477b9a3a494632d043e27eade0ad75ff84427` original verified-once receiver processes with the same checked `bb4d1466…` scientific/build inputs. Use the exact existing normal `load_prefetch` and its private slot binding. The sole arm change applies the same slot port used by `--reuse-prefetched-snapshots`. Use ordinary then slots and slots then ordinary, with a separate naturally idle Gauss lease per matched order and a cap of seven seconds per child. Require a current `deferred_storage_busy` event from the official driver on its NVMe ledger and a single nonblocking shared-lock success before each matched order. Respect any occupied lease or absent deferral. Run as `leo` on CPU 2 at nice 15 and best effort I/O level 7, with all numerical threads set to 1. Keep separate fresh process, allocation, native decoder, frame checksum, encoded and decoded hashes, `readv`, selection, sealing and through-exit costs in scope. Report the existing timing subscopes and per-arm totals. [Released experimental opt-in](prefetch-snapshot-publication.md) · [Original-prefix port](original_prefix_scaling.py)

Create a private `research-original-recording-prefix` inventory and its own session and acquisition digests. Bind all six original members in timestamp/index order, from zero through segment sequence end 384. Keep the parental full recording authority as custody only. Seal detections after the existing owned decoder and native receiver exhaust the exact scope and before decision, solver and publication. The original scope must include **384 issued / 362 admitted visits**, 22 exclusions, and the exact ordered 724 native stereo probes, with 92 full and 632 sparse-short calls. Check pre-selector detector rows against the first 384 visits of the signed archived original successor packet. Compare the independent prefix terminal detector documents byte for byte, permitting a prefix-specific held selection as long as all arms match it. The existing lookahead must submit and serve exactly five covered next-member buffers and never open or request the excluded seventh member. Full-recording positions, grids and speed gates are outside this receiver-only experiment. [Original archived signal checks](ds30-0049-receiver-factorial.md)

Run with the installed interpreter and exact script, changing only the listed matched order and its fresh output directory between leases.

```sh
orientation=forward
repo=/srv/postgres-nvme/leo-ds30-research-worktrees/prefetch-prefix-0049
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
out=/tmp/leo-v3-prefetch-prefix-0049-$orientation-02
sudo -n systemd-run --quiet --wait --pipe --collect \
  -p User=leo -p Group=leo -p Nice=15 -p CPUAffinity=2 \
  -p IOSchedulingClass=best-effort -p IOSchedulingPriority=7 \
  /usr/bin/flock -n /tmp/leo-algo08v2-2x-bench/gauss.lock /usr/bin/env \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 /usr/bin/timeout -k 1s 16s \
  "$release/venv/bin/python" -IB "$repo/reports/ALGO08/v3/prefetch_prefix_0049.py" \
  launch "$out" --orientation "$orientation"
```
