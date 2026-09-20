# Causal TLE freshness audit and controlled position replay

The recent 48-hour assigned cohort has older orbital elements than the
historical eight-hour cohort: median age **20.50 versus 9.93 hours**. Historical
ages span 3.26–34.89 hours; recent ages span 3.29–96.17 hours. These distributions
are conditional on their respective frozen candidate identities.

The RF-only export used a snapshot collected before the capture minus 505 s,
which supported the earlier wrong-time diagnostic convention. The newest
snapshot strictly before capture differs for 12 of 211 recordings. Moreover,
the latest collection can contain an older element than another already
collected snapshot. Collection freshness and element freshness are distinct.

## Audit rule

The read-only audit examines 166 archived Space-Track/Hugging Face snapshots
collected within seven days before the first relevant recording through the
last recording. For each frozen satellite assignment it chooses the largest
element epoch for which both element epoch and collection time strictly
precede that recording. Collection time and digest break ties. No measured RF
residual, receiver coordinate, or fitted position participates in this choice.
The archive reader verifies snapshot digests.

99 of 599 assigned tracks have strictly newer causal element epochs available.
The improvement among those updates has median 15.69 hours and maximum
47.08 hours; the minimum is only 0.864 ms, so "strictly newer" is not synonymous
with a materially newer orbit. Overall median element age falls to 18.94 hours.

The [complete freshness audit](2026_09_20_track_position_information/causal-tle-freshness.json)
records original/selected epochs, collection times, providers, snapshot digests,
and exact selected element text for every assignment.

## Controlled replay

Only the 99 strictly newer element sets replace the original orbit states.
All 99 propagate successfully over the observations and ±0.5 s timing interval.
The other states, RF measurements, identities, random partitions, starting
point, and previous clean-cohort selection remain fixed. Each source retains
its fitted constant frequency offset. These are conditional local replays of
FoV-assisted identities, not an independent wide-region solution.

| Cohort | Shared clock fitted? | Position error | Fitting RMS | Random evaluation RMS |
|---|---|---:|---:|---:|
| All | No | 5,110.8 m | 162.06 Hz | 163.76 Hz |
| All | Yes | 4,308.9 m | 162.05 Hz | 163.08 Hz |
| Previously selected clean | No | 5,114.3 m | 70.02 Hz | 85.06 Hz |
| Previously selected clean | Yes | 4,589.1 m | 69.87 Hz | 84.64 Hz |

All fits converge. The corresponding original shared-clock results were
4,194.9 m and 4,469.1 m. This experiment does not improve them. Newer element
epochs are a defensible input-selection rule, but do not by themselves guarantee
a more accurate orbit or validate a candidate identity. No production catalogue
selection was changed on the basis of this test.

Errors use the user-supplied antenna coordinate only after inference and a
spherical radius of 6,371,008.8 m. The [replay artifact](2026_09_20_track_position_information/fresher-causal-fit.json)
contains input digests, update indexes, rejection accounting, and all fits.

## Reproduction

Run `tools/audit_causal_tle_freshness.py` with `--archive /var/lib/leo/tle`,
`--evidence /tmp/leo-sky-position-48h/evidence-v2`,
`--assignments /tmp/leo-sky-position-48h/fov-polish.json`, and a fresh `--output`.
Reading the production archive may require sudo; it is never modified.

Run `tools/replay_fresher_causal_tles.py` with that JSON as `--audit`, the same
`--evidence`, and:

```text
--states reports/2026_09_20_doppler_error_budget/states.npz
--parent reports/2026_09_20_matched_positioning/inference.json
--information reports/2026_09_20_track_position_information/information.json
--output NEW_OUTPUT.json
```

Four tests cover collection-time versus element-epoch selection and reject
future-collected, future-epoch, or non-newer elements before a fit can publish.
