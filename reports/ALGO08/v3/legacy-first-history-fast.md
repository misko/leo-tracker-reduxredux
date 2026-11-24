# Bounded direct output and shared prefix SHA on original first use

On original DS30-0016 member 3, combining direct-to-window Zstandard
output and a shared prefix SHA-256 step saved **35.026 and 13.591 CPU ms**
in reversed orders through authenticated native detections, map reopen
and map-file sync. That is **12.34% and 5.14%**. The second order missed
the frozen absolute **20 ms** gate for a complete-recording run.
The prefix SHA change alone saved **8.10–8.28 CPU ms** at its measured
stage. Every arm reproduced the original signed sample evidence,
ordered receiver outputs and independent replay map. [Protocol](legacy-first-history-fast-protocol.md) · [Receipt](measurements/legacy-first-history-fast-0016.json)

## Where the work moved

The existing first-use producer already authenticates the complete
original encoded snapshot once, uses one continuous native full-history
decode, and opens its derived index on the same authenticated bytes.
The new work targets two costs still paid inside that traversal. Earlier
direct block delivery used a 102.4 MB decoded arena, and reusable
compressed allocation saved about 4 ms on its second resident read.
This experiment keeps ordinary independent window ownership and a
bounded decoded working set. [Original no-plan path](legacy-first-use-authority.md) · [Earlier full decoded arena](fused-block-input.md) · [Earlier snapshot reuse](legacy-snapshot-reuse.md)

- Full native blocks can land directly in the owned output allocation.
  Only the at-most-one-block carry at a logical window boundary must
  be copied. The next call retains the previous allocation as a
  libzstd external dictionary. This is offered only on a uniform
  window large enough to hold the declared original history and one
  complete possible carry. Variable or smaller extents use the
  existing ring. Independent read-only views remain valid after
  advancing or closing the producer.
- The SHA-NI paired routine updates the exact original window and
  complete member contexts together. At the compact map's 8 ms
  boundary, it finalizes a snapshot of the window state to get the
  unchanged prefix hash, then continues the two real contexts on the
  tail. The existing OpenSSL and hashlib paths cover misaligned,
  unsupported and old-library cases. The original frame checksum,
  compressed SHA, index SHA, full window SHA and complete decoded SHA
  remain required at their existing boundaries.

The measured ring history and decoder context used **882,664 bytes**.
With direct output they used **96,168 bytes**, plus up to one
**1,731,072-byte** allocation per live window, including its 128 KiB
carry space. The producer needs two allocations during a transition,
and downstream holders can retain windows as before. That gives
**3,558,312 bytes** for two direct windows and context, versus
**4,082,664 bytes** for two ring-delivered windows and context. Encoded
snapshot, exception and map workspace are common to both. This is a
working-buffer calculation within acquisition.

## Measured signed member

All **19,166** observed original manifest, index and payload pages
remained resident. The original compressed extent was **78,317,175**
bytes and the decoded extent was **102,400,000** bytes. All 64
original rows ran through verification, with seven retained exclusions,
eight stereo anchors with both 20 ms scans and 49 stereo short visits.
The 114 ordered native lanes contained 38 positive lanes and three
residual candidates. All ten arms produced the exact same measurements
and map. The pinned map was **427,753 bytes** with three sparse blocks
at original ordinals 120, 135 and 676. The independent consumer
reopened it and verified its first prefix after complete original
verification. The oracle pin was
used only to compare the newly generated map. [Independent prior map](legacy-fused-map.md)

| Mode | Native read CPU ms, forward / reverse | Decoded SHA CPU ms | Whole member CPU ms | Whole member elapsed ms |
| --- | ---: | ---: | ---: | ---: |
| Ring with released paired SHA | 70.035 / 64.876 | 32.774 / 32.725 | 283.919 / 264.349 | 284.710 / 264.354 |
| Ring with rebuilt paired SHA | 67.937 / 64.029 | 32.616 / 32.573 | 266.380 / 263.899 | 266.396 / 263.917 |
| Owned output with released paired SHA | 62.244 / 62.006 | 32.703 / 32.772 | 317.029 / 260.647 | 317.036 / 260.653 |
| Ring with prefix SHA reuse | 65.299 / 64.165 | 24.513 / 24.290 | 255.275 / 251.283 | 255.280 / 251.289 |
| Owned output and prefix SHA reuse | 61.379 / 62.011 | 24.505 / 24.523 | 248.893 / 250.758 | 248.908 / 250.767 |

Both repetitions used the same current native decoder object and one
receiver context per aperture. The release hasher was pinned and the
rebuilt hasher control accounts for its build change. The combined
native read and decoded hash stages saved **14.669 and 10.068 CPU ms**
relative to the rebuilt ring baseline. The first owned-only arm paid
**63.357 ms** for map serialization, reopen and sync, versus
**4.535–5.542 ms** on all other arms. The combined phases paid
**4.719 and 4.535 ms**. The timings preserve the outlier.

The normal archived complete first-use DS30-0016 process spent
**3.419 s** in authenticated acquisition and **8.243 s** through both
position fits, figures and exit. Applying the reproducible prefix-stage
rate to thirteen equally costly members would save roughly **0.11 s**.
The reverse-order combined whole-member saving projects about
**0.18 s** under the same assumption. The final member and fixed
producer overhead differ. These are scale estimates from resident
component clocks. The experiment had one resident original member and
no position or complete recording run. [Complete no-plan publication](legacy-first-use-original-panel.md)

## Reproduction

The frozen harness requires exact installed stock storage, the staged
original, CPU 2, nice 15, I/O priority 7 and one numerical thread. Its
output contains the source and library pins, ordered sample evidence
and native, hash and seal clocks. The harness checks the exact
installed receiver and pilot-input pins. Receipt SHA-256 is
`9b3234d51cc556f08b90ded2b1fbc02a4b0590981d0f798d59c78f26aeb6e676`.
The 31 focused tests cover cross-boundary history, retained immutable
windows, partial and empty extents, late checksum failure, stream and
window digests, and aligned and unaligned prefix SHA snapshots.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
  sudo -n -u leo ionice -c2 -n7 nice -n15 taskset -c 2 env \
  PYTHONPATH="$release/src:$PWD:$PWD/reports/ALGO08/v3:$release" \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.legacy_first_history_trial "$new_tmpfs_output"
```
