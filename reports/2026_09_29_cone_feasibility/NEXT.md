# Next modeling decisions from the completed cone checks

The cone/trend sweep is complete and does not solve short-set localization.
Its [twenty-model comparison](../2026_09_29_cone_trend/MODEL-COMPARISON.md)
shows that complete both-RX variants still have a worst-dataset eight-scan
median near 2 km or worse. Geographic improvements and held-frequency gains
must remain separate criteria. The unsurveyed reference and inherited center
do not provide blind validation.

## What the domain exclusion changes

With the nominal axes and retained banks, a complete all-track satellite
explanation at equal 20-degree half-angles is ruled out for all 72 scans
throughout the allowed position/timing domain. At 30 degrees, 54/72 scans
are ruled out; at 40 degrees, two DS9 scans are ruled out. A larger optimizer
budget cannot resolve these exclusions without changing assumptions.

At 50 degrees no case is excluded by this bound, and the earlier fixed-point
audit already found a whole-training-track candidate for every track. That
geometric support is not verified association, calibrated antenna response,
or a source of demonstrated sub-km accuracy. Nonexclusion by the bound alone
does not prove that a common geometry solution exists.

Do not fit a narrow hard-cone model requiring every track to be satellite
signal and then hide failed scans. A model allowing background tracks is a
different hypothesis and must report those assignments explicitly.

## Bounded next investigation

First inspect the two 40-degree exclusions using their existing observation
exports and candidate manifests. They are both RX0 tracks:

| Panel | Scan | Track SHA256 | Candidates | Best candidate lower bound over domain | Best angle at old fitted point |
|---|---|---|---:|---:|---:|
| DS9 early eight | scan-fw-2ab18976d4eb3bf8 | a9563aec999b3232981a7edc46ea49be0b07860f9968a969068db297b22155e0 | 22 | 40.060186° | 43.579861° |
| DS9 late eight | scan-fw-6376718c921309b1 | 4261f7784675acae1a36574039d74840f7f822b73fcd9668ab22846d7ed8ea86 | 18 | 41.924899° | 45.499530° |

These lower bounds apply only to the assumed pose and finite retained banks.
The first exclusion has a small angular margin; unmeasured world orientation
could matter. Do not treat either track as a verified non-satellite signal or
assume the physical beam must be wider. Inspect candidate identity, source
timestamps, receiver labeling, channel metadata and track quality before
choosing between bank incompleteness, pose error, sidelobe reception and
incorrect association. No new RF collection is needed for this inspection.

Then consider a matched, fixed-position hard-gate scoring check before a new
geographic fitting campaign. Compare hard 40/50-degree gates with the existing
soft gates at the same no-cone training-selected locations/timings. Preserve
the normalized unassociated alternative, training-only support, identical held
observations and explicit unsupported-track counts. This would be a diagnostic
of association and prediction, not a new location result. Freeze its tests,
inputs and evaluation rules before execution; it has not been run here.

A later hard-gate geographic fit needs a separately tested bounded search for
the discontinuous objective and must retain infeasible cases. Do not reuse
smooth-gradient convergence checks as if they prove optimization across cone
boundaries. A reception/non-reception model additionally needs actual observing
opportunities and detection-selection accounting; frequency prediction at
detected times alone does not establish satellite travel direction.

Independent receiver pose and beam-response evidence would distinguish the
remaining physical explanations. Widths here remain half-angles under the
declared interpretation; neither the nominal 20-degree axis separation nor
these sensitivity outcomes calibrates them.
