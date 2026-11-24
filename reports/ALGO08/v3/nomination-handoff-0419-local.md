# Frozen routed solver on blind DS30-0419

On the second hash-enrolled recording, the frozen candidate completed a
position fix in **16.178 wall s** versus **38.072 s** for the fresh
installed ALGO08v3 saved worker. Both used the original signed 20 ms
detector output, region and cutoff. The candidate reduced horizontal error
by **573 m at fixed zero** and **582 m with fitted `c`**. It accepted the
lean solver directly. No named fallback consumed a nomination checkpoint.
The elapsed ratio therefore measures the whole frozen candidate on one
blind recording. [Assignment](nomination-handoff-0419-protocol.md) ·
[Local staging amendment](nomination-handoff-0419-local-protocol.md)

## Exact local archive and timing boundary

The prior tmpfs-only admission found just 43 snapshot files and deferred
this exact assignment. The amended source was the existing collector
on local NVMe device **64512**, at
`/var/lib/leo/tle/archive/space-track`. The nominal 72-hour window with
the original upper cutoff, **2026-11-20 06:27:04.637108210 UTC**, gave
all **48** required filenames. The final collected snapshot was at
06:03:26 UTC. The filename digest exactly matched the original release
`sha256:d522aeef3c5da9b482cf58465bf7f8e06d752efc78131605ffc7e883c59a78b6`.
Each member's device, inode, extent and SHA-256 verified before its
bytes were admitted. The complete **85,839,871-byte** copy was resident
in one private tmpfs stage shared by both workers. Linux charged
86,282,240 physical input bytes to the copy process over that interval.
No RAID archive or waveform was opened. The detector packet has
**6,774 issued**, **5,220 admitted**, **10,440 radio probes** and
**4,258 factors**. [Prior tmpfs-only deferral](nomination-handoff-0419.md)

| Paid scope | Wall s | CPU s |
| --- | ---: | ---: |
| Collector directory and exact filename roster | 0.001 | 0.001 |
| Verify and copy all catalogue bodies | 0.223 | 0.068 |
| Common admission, including the rows above | **0.762** | **0.557** |
| Routed solve including input preparation and grid | 12.718 | 12.679 |
| Installed solve including input preparation and grid | 33.695 | 33.638 |
| Routed child through verified publication and exit | **16.178** | **16.137** |
| Installed child through verified publication and exit | **38.072** | **38.010** |

The candidate went first, as frozen by the odd-ID rule. Both children
ran under one CPU 2, nice 15, best-effort I/O priority 7 lease, with one
numerical thread. The candidate's regional input preparation took
**2.448 wall / 2.437 CPU s**, within the solve above. The named child
charged preparation in its solve clock and did not record a separate
counter for it. Publication inside the respective worker took
**14.867/36.444 wall s**, including solve and official artifacts.
The historical installed raw clock of **93.571 s** includes acquisition
and remains outside the saved comparison. The saved speedup is
**2.353×** through worker exit, **2.292×** charging common admission
to both workers, or **2.248×** charging it to the candidate alone.

The launches used the original remediation's exact source digests and
verified the installed ALGO08v3 specification before timing. The healthy
earlier-orbit census authorized lean. It captured **three** nomination
checkpoints over **eight** ranked nodes, with 12.2 ms CPU for the
geometry guard and 5.9 ms for checkpoint capture. The original joint
fit and later publication accepted without support repair, a named
fallback, or a live orbit extension. The handoff reused **zero**
checkpoints. Preparation used the ordinary catalogue, with no portable
index.

## Both calibrations and publication

| Calibration | Installed horizontal error | Routed horizontal error | Installed conditional RF RMS | Routed conditional RF RMS |
| --- | ---: | ---: | ---: | ---: |
| Fixed zero | 3,664.417 m | 3,091.068 m | 112.445 Hz | 112.802 Hz |
| Fitted | 3,546.851 m | 2,965.090 m | 112.508 Hz | 112.819 Hz |

Fitting `c` reduced horizontal error by **117.566 m** on installed v3
and **125.978 m** on the routed candidate. Conditional RF RMS increased
in both. The routed candidate uses the same observations within its two
calibrations. Relative to installed it kept 3,003 of 3,070 observations
per arm, dropped 67, and reassigned 63 of the retained observations
to a different satellite. It added no observations and changed no
roles. The signed terminal, numerical grid and path differ across
workers. Both produced the complete **179-point** grid, fit path and
all **eight** independently decoded PNGs, with each path and grid
binding its own position PNG. All eight images differed between
workers. The candidate used ordinary orbit sheets and accelerated
residual, position and track rendering.

The fresh installed result reproduced the archival installed signed
terminal, both positions and RF fits, ordered owner hashes,
numerical grid, path and all eight encoded and decoded PNGs. A
separate scoring pass joined the sealed reference after both
predictions and artifacts were sealed. The receipt records the
original input, commands, artifact digests and per-arm ownership.

## Cumulative evidence

| Saved worker clocks | Installed wall s | Routed wall s | Role |
| --- | ---: | ---: | --- |
| DS30-0255 | 50.721 | 56.232 | Development after observing the original holdout |
| DS30-0419 | 38.072 | 16.178 | Blind validation of the unchanged composition |
| Two-recording total | **88.794** | **72.410** | One development, one blind |

Across the two recordings both settings fixed in **2/2**. Both arm
errors were equal on 0255 and lower on 0419. For worker exit clocks
the ratio of summed wall times is **1.226×** and the reciprocal of
the median paired candidate/installed time ratio is **1.304×**.
The CPU ratios are **1.227×** and **1.305×** respectively. The
only measured fallback consumption remains 0255, where the handoff
removed 10.545 wall s from the original routed trial and still left
a 5.511 s deficit to installed. The blind case measures neither
fallback savings nor population accuracy.
[Development comparison](nomination-handoff-0255.md)

Execution froze at `76b28b6ebfd911a67ac1fc48f9127ced05eecae9`.
The follow-up score added independent archived media and sidecar
comparison outside the original prediction seal. After correction of
the postscore output path and terminal field, the scorer reread the
sealed products. Neither timed worker was repeated. Twenty-two tests
passed. [Source](nomination_handoff_0419_local.py) ·
[Tests](../../../tests/pipeline_eval/test_nomination_handoff_0419_local.py) ·
[Full receipt](measurements/nomination-handoff-0419-local.json.gz),
uncompressed SHA-256
`cf0f8f0673f3b1f6043d7766b6f4925083376c74d1d129d128fb5813dc0c9f70`.
