# First-use original input on the public North simulation

The normal 20/8 ms first-use entry completed North in **11.606 s elapsed
and 11.603 s CPU**. It derived and verified fresh maps for all 19 original
compressed members and published both calibration arms through eight
standard figures. Against the earlier installed ALGO08v3 process that
included independent readback in the clock, the elapsed speedup was
**1.568×**. The earlier stock clock with verification afterward gives
**1.390×**. The complete process was **0.386 s** faster than the older
ordinary-input 20/8 ms route. Acquisition itself took **0.195 s longer**
in this comparison. North is a simulation and supplies no additional
physical DS30 case. [Frozen protocol](legacy-first-map-north-protocol.md) · [Sealed trial](measurements/legacy-first-map-north.json.gz)

| Complete publication | Elapsed / CPU, s | Timed boundary |
| --- | ---: | --- |
| Installed ALGO08v3 | 18.201 / 18.161 | Launch through independent terminal and standard media readback |
| Earlier installed ALGO08v3 | 16.133 / 16.128 | Normal launch through exit, independent verification afterward |
| Prior ordinary original 20/8 ms history-risk | 11.992 / 11.987 | Launch through verified publication with ordinary renderer and cold causal orbit preparation |
| Fresh original 20/8 ms with derived maps | **11.606 / 11.603** | Normal first-use entry through verification, original orbit sheets, Cairo residual layout and map publication |

The candidate misses 1.6× against the readback-matched installed clock
by **0.230 s** and needs **2.505 s** more to halve it. The denominators
come from earlier single launches on the same original inventory, region
and causal archive. No additional installed or ordinary control ran.
[Readback-matched installed](strict-history-raw.md) · [Earlier installed](measurements/current-north-control.json.gz) · [Ordinary 20/8 ms](history-risk-raw.md)

## Original first use and charged work

All **1,200** original stereo visits in **19** members passed the stock
input geometry checks. The process authenticated **1,579,423,424 encoded
bytes**, then verified **1,920,000,000 decoded bytes** through the
original frame checksums, every signed per-window SHA-256 and all full
member SHA-256 values. The unchanged schedule issued 304 full and 2,096
short native lane calls. Its exact prehistory factor counts were 82 full
and 1,513 short, with the same **456** factors in the selected signed
native packet. The ordinary and current routes both select from the
original two-scan full anchors and preserve both antennas on each visit.

The producer derived **17 literal and two exception maps**, with no
ordinary fallbacks. There was one exceptional block each in original
members 1 and 11. The independent replay reader reopened every newly
emitted map on the same authenticated compressed snapshot and checked
the first original prefix. The complete **930,441-byte** directory
binds unchanged raw authority, ordered original inventory and custody
SHA-256
`fb80d852cc5bf13dbe127c38b82aecb5501d6f4f7726e784aaed2cb469325cba`.
Admission and the timed process supplied zero prior map files. The
verified portable orbit transfer reused **11** eligible bodies and
prepared **12** cold, without invalid bodies or portable fallback.

| Nested scope | Older ordinary 20/8 wall, s | Current fresh original wall, s |
| --- | ---: | ---: |
| Authenticated acquisition | 4.973 | 5.168 |
| Native detector calls within acquisition | 2.629 | 2.686 |
| Held-history selection | 0.071 | 0.073 |
| Decision and publication | 6.393 | 5.799 |
| Solve including complete grid | 3.583 | 3.562 |
| Eight standard figures | 1.701 | 1.046 |

The first-use route charged **0.177 CPU s** for map support setup,
**1.255 s** for native input decode and **0.622 s** for decoded hashes
including prefix hashes. Within acquisition, map discovery and history
planning took **33.5 ms CPU** and map serialization and reopen took
**81.5 ms**. Final durable bundle publication took **2.4 ms CPU**.
These clocks are nested. The through-exit gain covers the combined
original intake, orbit-index reuse and renderer. The orbit artifact
was available before launch. Its earlier reusable build took 4.320 s.
[Portable producer clock](legacy-first-use-original-panel.md)

All **385,609 waveform pages** and **188 signed-index pages** remained
resident on tmpfs. The original catalogue was also on tmpfs and showed
15,284 of 15,295 pages resident at admission. The process recorded zero
major faults and 128 process-wide input blocks. No RAID or QNAP source
was opened, and no waveform was copied, conditioned or recollected.
Controller prep before the diagnostic probe took **0.065 s elapsed**.
The separate setup-only probe took **0.359 s** and reached the actual
scanner without opening a waveform. The timed child separately paid its
actual start and setup. Two earlier admission attempts exited before
launch. The alternate user could not query residency on the existing
files, and the first source-owner check imposed full residency on all
catalogue pages. The final controller recorded catalogue residency
without warming it, and retained full I/Q residency checks.

## Scientific and media checks

The candidate matched the older ordinary 20/8 ms signed detector, both
positions, conditional RF, figure RF, and **342 ordered owners and roles
per arm** exactly. Its full **137-point** grid and complete path matched
after binding each to its own position PNG and removing the elapsed
metadata. The installed control shared 302 owners in each arm, with
zero missing installed owners, 40 additional owners and 17 changed
roles. Every common satellite identity matched. Both supplied region
centres and the complete late geographic check matched, including its
24 probes and `eligible_exterior_separation` stopping reason.

| North arm | Installed horizontal error | First-use horizontal error | Installed conditional RF RMS | First-use conditional RF RMS |
| --- | ---: | ---: | ---: | ---: |
| Fixed zero | 105.690 m | 111.954 m | 5.406 Hz | 9.133 Hz |
| Fitted | 140.779 m | 128.086 m | 5.167 Hz | 8.921 Hz |

All eight official PNGs were independently read, decoded and checked
against their manifests. All dimensions and PNG metadata matched the
older routed output. The four orbit PNGs were identical as encoded
files and decoded pixels. The layout deliberately changed the two
residual sheets, position PNG and track RMS sheet. Their changed-pixel
fractions were **14.38%, 14.62%, 19.47% and 17.54%**, respectively.
The same scientific row contents and original recording title bind the
published products. [Independent pixel and owner comparison](measurements/legacy-first-map-north-media.json)

## Reproduce

Run the controller under the existing North source owner and the
shared Gauss lock. It verifies the original local paths, exact native
libraries and archived reference clocks, then starts the ordinary
`legacy_first_map_entry.py` as a fresh child. The measured revision
was `df3da8ed7`. The uncompressed outcome SHA-256 is
`60430e118acc98b1677b404086ac16b44bb844a9a5690ba26f2307f016178878`.
The scoring action reads only sealed publications and map metadata.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
  ionice -c2 -n7 nice -n15 taskset -c 2 env \
  PYTHONPATH="$release/src:$PWD:$PWD/reports/ALGO08/v3:$release" \
  OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.legacy_first_map_north launch "$new_tmpfs_output"
PYTHONPATH="$PWD/src:$PWD:$PWD/reports/ALGO08/v3:$release" \
  "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.legacy_first_map_north score "$new_tmpfs_output"
```
