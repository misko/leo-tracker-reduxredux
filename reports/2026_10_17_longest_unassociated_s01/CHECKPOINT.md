# Longest unassociated S01 track: continuation checkpoint

The user requested a deep dive on why tracks remain unassociated, focusing on
the longest. Duration selection gives RX1 CH6 T001, 71 points / 72.033 s; two
other fragments tie at 80 points. This turn made concrete progress: full-bank
phase competition, a three-curve consensus with explicit clutter, matched c
overlays adding 231 compatible points, transfer checks and residual diagnostics.

Most supported candidate: STARLINK-33735 / 63474, effective phase -2.7 s.
Old phase box +/-0.615659 s excluded it. Target RMS 1556 -> 132 Hz; old
component constant +5114 -> -1207 Hz. All original target points are retained.
The quartic is supported (131 Hz RMS, max leverage .669, raw affine RMS7372Hz).
No additional per-track slope is fitted; old residual slope86.1Hz/s exceeds
the small-LNB-drift hypothesis by a large margin.

Two data-consistent curved companions CH2 T001 / CH7 T001 support the phase.
Each of the three passes with phase learned from the other two (conditional on
frozen hardware). The fourth old nominee CH3 T002 is incompatible: RMS1995Hz,
bias+8011Hz. Whole-member clutter scoring retains its 27-point cost, without
vetoing the 153 coherent curved points. Full target audit: sole passing candidate
among1707, all601 phase states, both c arms; even fully free competitors fail.

The per-fragment frequency-compatibility overlay gains 231 =153curved+78linear
points, 2291 ->2522 /4797, 52.5745%. No old IDs/labels are lost. Shared-constant
merging gives85/79groups c0/fc. These are fixed-known-GPS diagnostics. Do not
feed their labels/phases into a claimed blind geographic search.

Critical qualification: pooled153-point curved residuals are correlated. At
-2.7s step4.08 andlag1.492 fail pooled independent-white-noise checks. At-2.75s
slope/step pass butlag1.476 >4/sqrt153=.323. A shared residual polynomial up
to degree4 fails to remove this correlation and is not favoured after an
incremental parameter penalty. Do not claim one noise-white merged carrier or
authenticated identity. The cause of the correlation is unproven.

All primary jobs terminal: candidate audit71750; phase transfer4135; consensus
profile61497; rendering25739; pooled auditscompleted. 70 focused tests pass.
Original analysis source versions are archived where current changes only bind
loop variables or correct visibility sorting. Numeric phase matrices preserve
all candidates. Published baseline reports remain unchanged.

Next user-review targets: longest remaining duration CH4T001; largest by count
CH2T000 andRX2CH3T000. Algorithmically: curve-first family nomination plus
explicit whole-curve clutter, then full-bank joint phase competition and frozen
linear extension. Port rescue into independently selected blind states before
new position claims. Ground-truth-conditioned findings cannot seed that claim.

The larger active goal remains unachieved: <0.5km position and wider DS22/DSX01
evaluation. Concurrent DS22 cold-pilot/influence work is recorded separately at
../2026_10_17_family_conflicts_ds22_expansion/. No external blocker.
