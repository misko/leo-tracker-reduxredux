# Exact first-use finalist on two resident physical originals

The normal first-use entry completed the **DS30-0016 fix in 7.777 s**
and the **DS30-0107 withhold in 0.542 s**. The two measured children
total **8.319 s**, a **1.472× summed** and **1.842× median** elapsed
speedup against installed ALGO08v3 on the same original recordings.
The prior no-plan first-use pair took 8.806 s, so the integrated
result saves **0.487 s** on those observed clocks. Both science
comparisons passed. The sum misses the 1.6× gate by **0.667 s**
and the 2× gate by **2.198 s**. The 1.472× sum falls outside the
frozen interval for an additional order reversal.
[Protocol](legacy-first-map-finalist-protocol.md) · [Sealed outcome](measurements/legacy-first-map-finalist.json.gz)

| Original | Installed v3 elapsed / CPU, s | Prior no-plan first use elapsed / CPU, s | Integrated first use elapsed / CPU, s |
| --- | ---: | ---: | ---: |
| DS30-0107 | 1.497018 / 1.495600 | 0.562754 / 0.561340 | **0.541532 / 0.540251** |
| DS30-0016 | 10.744677 / 10.742462 | 8.243089 / 8.217620 | **7.777000 / 7.774974** |
| Sum | 12.241696 / 12.238062 | 8.805843 / 8.778960 | **8.318532 / 8.315225** |

The clocks cover each child's launch through exit, including verification,
detector, numerical and media publication when applicable, and map seal.
The controls are earlier single runs on the same input and worker settings.
Against the previous first-use pair the CPU gain is **0.464 s** and
summed speedup is **1.056×**. Against installed the summed CPU speedup
is **1.472×**. The shared controller used the existing tmpfs mounts
and one CPU 2 slot with nice 15, I/O priority 7 and one numerical thread.
Both completed children recorded zero major faults and process input
blocks. External artifact compilation for the final attempt took
**0.350 s wall and 0.322 s compiler CPU**. The timed children separately
verified and loaded their existing artifacts.
[Prior complete first-use controls](legacy-first-use-original-panel.md)

## The actual active paths

- DS30-0016 kept the original 808 issued visits, comprising 713
  admitted stereo visits and 95 original invalid captures. All 13
  compressed members used direct-to-owned decoded windows, with
  the previous owned window as bounded frame history. The pinned
  paired SHA routine reused the prefix state on each member and
  kept the encoded, index, frame, individual raw window and whole
  raw member checks. All five literal maps and eight exception
  maps reopened on the same encoded snapshots and matched the
  independent maps byte for byte.
- DS30-0107 kept the original 29 visits, including the signed
  136,857-sample and empty invalid visits. The unequal original
  extents selected the existing bounded ring, and prefix SHA reuse
  ran on its sole member. All 27 admitted stereo visits and the
  genuine withholding decision matched, and the literal map
  reopened with the exact independent digest. The receiver-side
  withhold invoked neither solver hook. It emitted null results
  for both arms, with zero figures, grid or path.
- DS30-0016 executed the exact causal election and both original
  history elections. The measured adapter skipped 190,301 dominated
  newest-election row visits and projected 20 distinct bodies onto
  the original selected catalogue. The native diagnostic grid
  checked four observer geometries exactly, performed 708 more
  native projections, 356 native selections and 356 template fills,
  and checked the first matrix in each arm. Both optimizations
  reported zero fallback on fulfilled work. The normal renderer
  kept four ordinary orbit sheets and the earlier Cairo residual
  and position/track layout. In-flight retry was disabled.

| DS30-0016 scope | Old first use | Integrated first use |
| --- | ---: | ---: |
| Authenticated acquisition elapsed | 3.418814 s | 3.083625 s |
| Native original history decode CPU | 0.850565 s | 0.759901 s |
| Decoded SHA CPU | 0.435039 s | 0.314688 s |
| Signed solve including grid elapsed | 2.206752 s | 2.030368 s |
| Render eight PNGs elapsed | 0.852846 s | 0.844184 s |
| Decision and publication elapsed | 4.206375 s | 4.090032 s |

The input decode and SHA clocks are disjoint components within
acquisition. Solve and render are nested inside decision and
publication. These historical-control differences price the combined
change and ordinary run-to-run variation. Separate component gains
come from the narrower studies below. DS30-0107 acquisition changed from
0.133549 to 0.136527 s elapsed despite its 0.021 s lower total.
[Bounded input prototype](legacy-first-history-fast.md) · [Causal election](causal-body-election.md) · [Exact grid](exact-grid-0138.md)

## Verified science

The DS30-0016 raw authority, native packet, both positions, conditional
RF, 115 ordered owners and roles per arm, all 179 diagnostic grid nodes,
same numerical path and all eight encoded and decoded PNGs matched the
sealed ordinary 20/8 control. Both sidecars bound their official position
image. Fixed zero returned the original position **0.490 km** from the
operator-site reference at **134.021487 Hz** conditional RF RMS. Fitted
calibration returned **0.980 km** and **133.739967 Hz**. The withheld
case and both complete map bundles independently matched their earlier
original-file controls. No prepared waveform index entered either
candidate.

## Launch and limitations

The controller first attempted both children at `54e7522d8`. The installed
Python module shadowed the prefix wrapper, stopping the candidates in
**0.399 and 0.429 s elapsed**, on the first decoded window before either
signed acquisition completed. Explicitly loading the private prefix
binding and exercising it in the waveform-blocked startup probe resolved
the import. The second revision `3c2206c0c` completed DS30-0107 in the
reported clock. Its DS30-0016 child reached the publication boundary and
then rejected an incorrectly resolved installed solver import after
**4.270 s**. The last correction resolves the installed publication before
binding research solver helpers. That publisher is never invoked by the
unchanged DS30-0107 receiver-side withhold. The controller retained its
already sealed exit, products and precise source pins and launched only
the outstanding DS30-0016 at `e78c624b2`. The summed ratio uses one
successful child per case. The failed stage clocks remain separately
available. All I/Q accesses used the original resident copies.
[Failed-launch evidence](measurements/legacy-first-map-finalist-failures.json)

Use the same two private read-only mounts and the shared CPU 2 lease.
Run `legacy_first_map_finalist.py launch FRESH_TMPFS_ROOT` for the
predeclared pair and run its offline `score` action afterward. The
underlying entry is `legacy_first_map_entry.py` with the explicit
`--legacy-first-map-fast` artifact roster and `--legacy-first-map-fast-sha256`.
The score binds the actual commands, libraries, original sources and
read-only scientific checks. The uncompressed outcome SHA-256 is
`bcb774bb770a4ac65bdeeab5bc60b52cf0c077cc236cff456896e76b2906db01`.
Forty focused and adjacent tests passed.
