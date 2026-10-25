**A separate whole-scan question finds three unused curved RX2 sources.**

The original result remains zero unused curved RX2 sources with overlapping or
adjacent reference time support. That condition is appropriate for simultaneous
receiver comparisons; it does not rule out a physical-orbit prediction across
a later time gap. The coordinator therefore explicitly froze a separate
question, removing only that time restriction. No CFO or candidate-label score
enters either selection.

All three complete whole-scan sources are retained:

| Complete RX2 owner | Native IDs | Time interval, s | RF center, GHz |
| --- | ---: | ---: | ---: |
| CH3/T002 | 24 | 220.492868–242.819219 | 11.4403125 |
| CH5/T001 | 57 | 235.467098–293.937196 | 11.9403125 |
| CH4/T000 | 43 | 236.130545–264.829165 | 11.6903125 |

The union contains 124 distinct native IDs, with no overlap with either original
accepted-ID ledger or the historical 189 RX1 IDs. Exact component names, every
native ID, timestamps and original exclusion flags are in
[whole_scan_inventory.json](whole_scan_inventory.json). The full 146-source
selection/exclusion ledger is preserved there; nothing is trimmed or chosen by
closeness to 60108. Processing took 0.007 s and four source-owned tests pass.
These are available sources, not identified satellites or accepted associations.

Before an RF comparison, the proposed cheap check is geometric feasibility of
the fixed 60108 hypothesis at the previously saved c0 RF position. Use the
hash-bound causal `bank.npz` row for NORAD 60108 and original domain [-15,+15] s,
with no new propagation, future element, GPS or target CFO. The existing public
`leo.analysis.research.orbit_phase_geometry.phase_shifted_states` port specifies
linear state interpolation plus the original Earth-rotation correction.
`leo.sky.frames` supplies observer/up geometry. The saved endpoint can be
converted using the unchanged regional-center coordinate rule.

For a certificate, partition phase at the actual bank knots shifted by each
native timestamp. Bound the topocentric up projection on each interpolation
piece with its rotation/first-derivative/second-derivative bound and floating
rounding guard. A native timestamp certified below the horizon for every
allowed phase makes a complete owner's nominal visibility support empty.
Unresolved pieces or bank extrapolation must remain unresolved, rather than
being silently discarded. A dense grid alone cannot establish the certificate.
A 30 s, single-BLAS-thread check over this fixed three-source pool is sufficient
as a proposed cap; no candidate search or position optimization is needed.

The check has not been run by this metadata branch. Any result concerns the
declared nominal causal-bank-plus-phase visibility event. It does not integrate
visibility over the Gaussian physical-mode prior, establish true orbit
visibility, model GLRT detection probability or authenticate a satellite.

[Separate protocol](whole_scan_protocol.json),
[selected-owner CSV](whole_scan_selected.csv) and
[seal](whole_scan_seal.json) preserve the explicit question change. The
[original time-supported findings](FINDINGS.md) and their sealed artifacts remain
unchanged. No RF score, IQ processing, position fit, GPS read or operational
association occurred.
