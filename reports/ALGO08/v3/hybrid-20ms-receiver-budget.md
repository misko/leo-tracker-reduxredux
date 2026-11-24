# Original 20 ms receiver with the charted solver at half-time

The charted solver on each authentic installed 20 ms packet passed the
existing position comparison in both calibration arms. The observed
installed launcher had already used more than half its verified raw
elapsed budget by the time it wrote the detections, before solver or
rendering. Under a serial splice that retains the saved solve and render
clocks, the installed launch-to-detections prefix would have to shrink
by **7.144 s on DS30-0049, 32.859 s on DS30-0086, and 53.222 s on
DS30-0220**, even if all additional work were free. These are required
reductions under the stated timing assumption. The original 20 ms
receiver and charted solver have no combined measured raw runtime here.

## Measured raw and saved clocks

Wall seconds. The two verified raw columns include normal launcher exit
and the common publication verifier. The mixed acquisition column is a
nested phase of the charted raw run. Saved full-detector solve and render
are disjoint phases of a saved worker on the installed detector digest.

| Case | Installed 20 ms raw | Charted mixed raw | Charted mixed acquisition | Installed launch to native data write | Charted full saved solve | Charted full saved render | Charted full saved scientific publication |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DS30-0049 | 18.679 | 13.600 | 6.046 | 10.945 | 3.980 | 1.559 | 6.853 |
| DS30-0086 | 91.270 | 58.836 | 42.676 | 64.166 | 11.739 | 2.590 | 16.050 |
| DS30-0220 | 117.961 | 56.418 | 40.379 | 69.281 | 41.292 | 1.630 | 44.767 |

The saved full-detector worker exits were 7.35 s wall / 7.04 s CPU,
16.736 s / 16.114 s, and 45.626 s / 44.375 s, respectively. Those
separate worker observations include one dedicated saved-entry bootstrap.
They do not enter the hybrid budget. The raw 0049 and 0086 pairs ran in
one lease per pair, with 0049 originally installed first and 0086
successor first. DS30-0220's raw pair used separate leases. The saved
phases were measured in separately launched workers, so the difference
between raw and saved spans cannot identify a pure receiver speedup.

Each saved result binds the originally published 20 ms native digest,
inventory, raw authority, offered region and causal cutoff. The corpus
comparison preserved both arm decisions, 179 grid sites and eight PNGs.
The fixed/fitted position error changes were **0 / 0 m**, **+48.5 /
+47.3 m**, and **0 / 0 m**. DS30-0049 had the complete four-cell proof.
DS30-0086's fourth cell sealed separately. DS30-0220's full-detector
charted cell was qualified on exact ordinary fallback, with
`repair_rejection_cap` and **33.204 s** of named fallback inside solve.
The fourth-cell run was separately admitted and still pending at this
audit. Its installed-solver/mixed-detector clock cannot change the
half-time arithmetic for the charted solver/full-detector cell. All saved
results carry zero raw timing credit.

## Necessary receiver and other wall budget

The range below gives two named charges. The left endpoint charges the
whole saved scientific publication and can overlap the old receiver's
asset checks and native serialization. The right endpoint charges only
the disjoint solver and render clocks and leaves the rest of publication,
startup, ingress, and verification in the receiver and other budget.
The endpoints are scenarios. The prefix saving and free-solver checks
use disjoint recorded scopes and charge no separate saved startup.

| Case | Raw half-time | Receiver and other budget under the two charges | Excess of observed prefix even with free solver and render | Minimum prefix reduction with solve and render retained |
| --- | ---: | ---: | ---: | ---: |
| DS30-0049 | 9.340 s | 2.487 to 3.801 s | 1.605 s | 7.144 s |
| DS30-0086 | 45.635 s | 29.585 to 31.306 s | 18.531 s | 32.859 s |
| DS30-0220 | 58.980 s | 14.214 to 16.058 s | 10.300 s | 53.222 s |

The original scanner evaluates `acquire(...)` before writing
`detections.json` and before solve and render. Its immutable writer
updates the inode data, then fsyncs and links it. The timestamp therefore
prices launch through that data write, including startup, input
authentication and acquisition, but excluding any remaining persistence
on that file. Pure full-detector acquisition wall has no isolated timer
in these three original runs. The charted full saved scientific block
starts inside the saved adapter and redoes scanner assets, graph guards,
native handoff and publication. Adding it or the entire saved child to
the installed prefix would count some overlapping work twice. The normal
common verifier remains in the residual budget. The offline position
scorer has a different scope and does not fill that verifier slot.

## CPU capacity

CPU seconds use the same matched verified installed CPU denominator. The
installed worker and child process tree were pinned to one processor by
the sealed campaign driver. The stock CPU before native write lacks a
direct timer. The table derives its conditional interval by allowing at
most one CPU second per elapsed second on either side of the recorded
write, with 10 ms of clock slack and aligned realtime and monotonic spans.
This interval describes all child CPU before the write, including
startup. It does not give detector-kernel CPU. No mixed-receiver CPU was
substituted for it.

| Case | Verified installed / mixed CPU | Half installed CPU | Saved full solve + render CPU | Maximum remaining CPU | Installed pre-write CPU capacity interval | CPU deficit at least, retaining solve + render |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS30-0049 | 16.906 / 12.840 | 8.453 | 5.514 | 2.939 | 9.162 to 10.955 | 6.223 |
| DS30-0086 | 75.732 / 51.713 | 37.866 | 14.194 | 23.672 | 48.634 to 64.176 | 24.962 |
| DS30-0220 | 99.723 / 51.322 | 49.861 | 42.442 | 7.419 | 51.556 to 69.291 | 44.137 |

The charted mixed raw DS30-0220 run cleared the observed wall target by
2.562 s. It used a different detector packet and did not take the saved
full-detector fallback. Even removing all 33.204 s of that fallback
would give DS30-0220 only 49.262 s for receiver and other work. Its raw
prefix consumed 69.281 s. Recovering the full detector on DS30-0049
restores the installed positions. Its raw prefix already exceeds
half-time even with instantaneous downstream work.
No new receiver, solver, lease, orbit data, or waveform access was used.

The sealed receipt is `measurements/hybrid-20ms-receiver-budget.json`
with SHA-256 `9a4c31786b788c8a0c4200e61e2ad94e9d6267e29d073b42deb8f59e7394e914`.
It includes the three native-boundary timestamps, both original-file
process and verifier clocks, saved phase scopes, the detector and result
pins, and the arithmetic outputs. The method was frozen in `af492b8c9`.
Source inspection of the immutable writer and single-CPU driver tightened
the scope in `a96fda328`. Seven component tests passed.
