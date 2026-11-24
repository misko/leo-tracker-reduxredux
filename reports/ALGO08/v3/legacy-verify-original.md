# Verify the original once for a single scientific publication

The opt-in verified-once route completed both resident physical originals
and matched their exact signed science. It removes replay-map construction
and publication while keeping the original full integrity checks. It took
**8.575 s** combined, versus **9.136 s** for the fresh same-build runs with
maps and **8.319 s** for the earlier mapped finalist. DS30-0016 finished
**0.562 s** sooner than its fresh mapped control, but authenticated
acquisition took **0.061 s longer**. The solve took **0.604 s less**.
These clocks establish the simpler single-analysis path and price its
actual removed work. They provide no repeatable input speed gain.
[Frozen protocol](legacy-verify-original-protocol.md) · [Verified paired receipt](measurements/legacy-verify-original.json.gz)

| Original and outcome | Verified once wall / CPU, s | Same build with maps wall / CPU, s | Earlier mapped finalist wall / CPU, s | Installed v3 wall / CPU, s |
| --- | ---: | ---: | ---: | ---: |
| DS30-0107 withhold | 0.527095 / 0.525004 | 0.525718 / 0.521870 | 0.541532 / 0.540251 | 1.497018 / 1.495600 |
| DS30-0016 fix | 8.047974 / 8.046283 | 8.610301 / 8.593818 | 7.777000 / 7.774974 | 10.744677 / 10.742462 |
| Sum | **8.575069 / 8.571287** | 9.136019 / 9.115688 | 8.318532 / 8.315225 | 12.241696 / 12.238062 |

The verified-once elapsed speedups are **1.065× summed and 1.032×
median** versus the fresh mapped controls, **0.970× and 0.996×**
versus the earlier mapped finalist, and **1.428× and 1.816×**
versus installed v3. The corresponding CPU ratios are **1.064× and
1.030×**, **0.970× and 0.997×**, and **1.428× and 1.818×**.
Reaching 1.6× by elapsed sum against installed would require another
**0.924 s**. All measured child clocks cover launch through exit.
The study ran one fresh pair per recording, verified-once first on
DS30-0107 and map production first on DS30-0016. All children used
the same checked acceleration build under one CPU 2 lease, nice 15,
I/O priority 7 and single numerical threads. Artifact build cost
**0.350 s wall and 0.325 s compiler CPU** outside the child clocks.
[Earlier mapped finalist](legacy-first-map-finalist.md)

## What remains mandatory

The normal first-use entry authenticates the complete original manifest
and signed index, complete compressed snapshot, every decoded window,
complete decoded member and original frame checksum. The native reader
uses a bounded standard frame-header walk to establish a supported
single frame, then decompresses it one time. It retains no replay
block plan or exception buffers. It keeps independent read-only owned
windows with bounded previous-window history on uniform extents,
uses the original ring for mixed extents, and takes the existing
verified stock reader for unsupported frame structure. The latter
borrows an already authenticated compressed snapshot when available.

Per-window SHA and whole-member SHA share the same exact paired
implementation. The candidate skips replay-only prefix digests,
reopening and the detached bundle write. Before any terminal can
be attested, the receiver must consume every ordered original
member and agree with the full signed raw authority. A late failure
clears the provisional acquisition evidence. The ordinary signed
and scientific publication remains available, including the original
authority, terminal and eight products on a fix. The same-build
mapped mode also produces detached replay custody, which permits
later selective analysis under that index's own verification contract.
A future independent analysis of verified-once output can reread
and reverify the original compressed members normally.

## Observed work and parity

| DS30-0016 scope | Same-build with maps | Verified once |
| --- | ---: | ---: |
| Authenticated acquisition elapsed | 3.452811 s | 3.514017 s |
| Original native decode CPU | 0.891637 s | 0.925104 s |
| Original decoded SHA CPU | 0.334081 s | 0.327760 s |
| Native history setup and map description CPU | 22.055 ms | 1.954 ms |
| Map serialization, reopen and final seal CPU | 55.928 ms | 0 ms |
| Solve including complete grid elapsed | 2.528045 s | 1.923937 s |
| Eight standard figures elapsed | 0.834107 s | 0.889938 s |

Measured setup and map-output components fell **76.0 CPU ms** on
DS30-0016 and **3.7 ms** on DS30-0107. Other measured input work varied.
DS30-0107 acquisition took **0.128061 s** with maps and **0.126017 s**
without them. Both nominal source copies and their full signed indexes
remained resident. DS30-0107 verified-once charged one major fault and
128 process input blocks, and DS30-0016 with maps charged 56 input
blocks and zero major faults. The other two children charged zero of
both. These are process-wide counters. All waveform and archive paths
were the existing private tmpfs inputs. No RF, backing archive read,
prior waveform map or new installed comparison entered the trials.

DS30-0016 directly owned decoded windows for all 13 original
members. The candidate retained 808 original issued visits, including
95 exclusions, the identical ordinary 20/8 packet and both calibrated
positions and RF values. All 115 ordered owners per arm, the full
179-point grid, numerical path, and all eight encoded and decoded
PNGs matched. The fixed-zero and fitted endpoints remain
**0.490 / 0.980 km** from the prior reference, with conditional RF
RMS of **134.021487 / 133.739967 Hz**. The same exact election and
native grid activated for the fix in both modes.

DS30-0107 used the original bounded ring and consumed all 29 issued
visits, including the partial and empty excluded visits. Both
candidate and control withheld for the same legitimate reason,
with identical raw evidence, no scientific solver hooks, null
calibration arms and no figures, grid or path. The no-map reader
emitted no replay files in either case.

## Reproduce

Use the same private read-only original mounts and shared Gauss CPU 2
lock. Run `legacy_verify_original_trial.py launch FRESH_TMPFS_ROOT`
from the installed-interpreter environment in the
[mapped finalist](legacy-first-map-finalist.md) and follow it with
the offline `score` action. The private normal CLI option is
`--verify-original-once`, with the existing fast roster and decoder
pins. It needs no detached replay decoder or replay plan.

The measured revision was `559b7797e`. An offline scorer initially
compared a per-launch terminal timestamp and embedded image evidence
containing independent read clocks. The final scorer compares those
timings separately while requiring numerical product and encoded/RGBA
image equality. Every successful timed child and sealed product was
retained. The corrected score required no waveform read or timed replay.
The uncompressed receipt SHA-256 is
`4446a97aeba1b496a4c96ed949b43d3d6984432b4ac8f3087d8c8fafbd6c1555`.
Forty-six focused and adjacent tests passed. They include no-map
mixed, partial and empty extents, compound-frame fallback, and
original encoded, decoded-window, decoded-member and late checksum
corruption.
