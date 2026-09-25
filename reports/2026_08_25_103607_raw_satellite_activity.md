# Three-path raw satellite activity in dwell 103607

## Outcome

Three independently processed receiver paths in
`cap-20260825T103607-9bd90a1a50e4` recover the same catalogue-shaped
candidate, NORAD 66811 / STARLINK-36045, from raw retained GLRT64 peaks over
`[46.0, 60.0)` s. Two paths are on 11.4596875 GHz and the third is on
11.6903125 GHz. The underlying dealiased branches have 8.700 s of common UTC
overlap and an RF-normalized linear-rate spread of only 1.99 Hz/s.

This is strong multipath, cross-band evidence for one orbital-frequency event
and a useful candidate association. It is not spacecraft identification: the
catalogue search is pruned, no payload is decoded, the site is externally
supplied, the TLE acquisition provenance is not verified by this replay, and
the receiver-relative delay/CFO nuisances remain confounded.

## Frozen inputs and outputs

- 5d4d/RX0:
  [input](figures/2026_08_25_103607_satellite_activity/capture-input-5d4d-rx0.json),
  [declared-range replay](figures/2026_08_25_103607_satellite_activity/raw-catalogue-46-60-5d4d-rx0-score-v3.json),
  [wide post-hoc replay](figures/2026_08_25_103607_satellite_activity/raw-catalogue-46-60-5d4d-rx0-score-v3-wide-posthoc.json)
- 5d4d/RX1:
  [input](figures/2026_08_25_103607_satellite_activity/capture-input-5d4d-rx1.json),
  [wide post-hoc replay](figures/2026_08_25_103607_satellite_activity/raw-catalogue-46-60-5d4d-rx1-score-v3-wide-posthoc.json)
- 19f2/RX1:
  [input](figures/2026_08_25_103607_satellite_activity/capture-input-19f2-rx1.json),
  [declared-range replay](figures/2026_08_25_103607_satellite_activity/raw-catalogue-46-60-19f2-rx1-score-v3.json),
  [wide post-hoc replay](figures/2026_08_25_103607_satellite_activity/raw-catalogue-46-60-19f2-rx1-score-v3-wide-posthoc.json)
- Joint three-path comparison:
  [wide post-hoc replay](figures/2026_08_25_103607_satellite_activity/raw-multipath-catalogue-utc-46-60-score-v3-wide-posthoc.json)

All three inputs are sealed Standard-path extractions from the existing radio
corpus. Each replay retains 560 scheduled probes and 5,600 returned candidate
rows. Every probe reaches the acquisition prefix of ten candidates, so this is
the complete persisted bounded prefix, not a physically exhaustive peak
inventory. Detector score costs use the same disjoint frozen V3 calibration as
the 073628 and 085623 studies. Satellite and episode costs remain provisional.

## Independent path results

The predeclared `[-2,+2]` s nuisance search was first run on the two dense
cross-radio paths. Both selected NORAD 66811, but both delay fits landed on the
`-2.0` s boundary. A clearly labeled post-hoc `[-5,+5]` s sensitivity run then
moved the optima just inside the wider range:

| Path | RF | Modeled groups | Best delay | Assignments / misses | Residual RMS | Runs | Final delta from raw-clutter null | Runner-up zero-satellite-cost delta |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 5d4d/RX0 | 11.4596875 GHz | 433 | -2.3 s | 424 / 116 | 22.47 Hz | 1 | -1265.77 | -523.13, NORAD 59901 |
| 19f2/RX1 | 11.6903125 GHz | 547 | -2.4 s | 369 / 167 | 65.09 Hz | 2 | -946.97 | -367.85, NORAD 59901 |
| 5d4d/RX1 | 11.4596875 GHz | 241 | -2.1 s | 147 / 173 | 52.60 Hz | 6 | -204.25 | -48.99, NORAD 59331 |

For NORAD 66811, the corresponding zero-satellite-cost deltas are -1271.02,
-952.22, and -209.50. Thus it remains well separated from the other refined
catalogue objects on all three paths. The first two paths independently prefer
nearly the same widened delay; the third is much weaker but agrees on both
catalogue object and nuisance region.

NORAD 66811 is predicted at 65.77--68.00 degrees elevation, using an element
epoch 31.91 hours before the middle of the replay window. A targeted
wrong-time diagnostic shifted only this candidate's frozen orbit epoch and
refit its delay/CFO nuisances: at +/-60 s its zero-satellite-cost advantage fell
by more than 96%, and at +/-120 s all three paths preferred `N=0` after the
satellite penalty. This is useful shape specificity, but it is not a
full-catalogue wrong-time look-elsewhere control. Likewise, a targeted
`[-10,+10]` s sensitivity run covered only each path's original top three; it
kept 66811 near `-2.3 s` and did not overturn the ranking.

The modeled runs are legal under the five-cell minimum, but they should not be
read as measured transmitter onsets or durations. In particular, the 5d4d/RX0
run fills `[46.5,60.0)` and the 19f2/RX1 result ends at the analysis boundary.
The model has no right-censor claim and the input window was chosen after the
physical trajectory was already visible.

## Joint shared-activity result

The three paths were then placed on one absolute-UTC 100 ms grid over a 13.8 s
common window. The bounded comparison supplied NORADs 66811, 59901, and 60096,
searched the post-hoc `[-5,+5]` s delay grid, and proposed independent CFO
offset modes for each receiver path. Each catalogue generated 808 fixed
delay/path-offset states; the four best single-catalogue states per object were
retained. The exact joint decoder evaluated all 64 retained-state combinations.

It selects only NORAD 66811, with one shared delay of `-2.4 s`, two legal runs
covering cells `[3,23)` and `[24,138)`, and a total improvement of 2328.08
pseudo-cost units over the raw-clutter null. Path-local support is:

| Path | Assignments / active misses | Path delta from null | Fitted CFO constant |
|---|---:|---:|---:|
| 5d4d/RX0 | 421 / 115 | -1279.38 | +382,539 Hz |
| 19f2/RX1 | 367 / 169 | -965.75 | -143,166 Hz |
| 5d4d/RX1 | 185 / 351 | -111.22 | -179,103 Hz |

The strongest retained single-catalogue deltas for the two supplied confusers
are -860.07 (NORAD 59901) and -837.94 (NORAD 60096), versus -2328.08 for
NORAD 66811. Distinct physical peak groups remain globally exclusive between
satellites, so the joint solver cannot manufacture `N=2` by giving the same
modeled group to two catalogue objects.

This is exact only inside the retained three-catalogue/four-state bank. The
outer catalogue shortlist and per-catalogue nuisance-state pruning are not
globally exact. The shared-occupancy model also makes a deliberately strong
assumption: whenever the satellite is active, it is expected at every usable
probe on all three paths, and the weak path consequently pays 351 explicit
misses. A future band-occupancy state is needed before applying that assumption
to arbitrary cross-band dwells.

## Interpretation

The important result is replication across independent raw inventories and
RF bands, not the fitted delay value. A roughly -2.3 s orbital-time shift is
orders of magnitude larger than capture timing uncertainty. Because a constant
CFO offset is independently fitted on each path, the delay mainly adjusts the
short-arc Doppler shape and is receiver-relative; it is not evidence that the
recording clock was wrong by two seconds.

The current exact solver is exact only after a small catalogue and nuisance
state bank has been retained. Here, the three paths have already been put into
one joint model with a shared activity mask and delay, separate per-path CFO
constants, and explicit competition from the two retained confusers. The next
step is to expand and audit the outer catalogue/nuisance search, add explicit
path-by-cell band eligibility, and run the locked dwell-cluster null study
before interpreting an objective delta as a calibrated false-activation rate
or posterior odds. The leading NORAD 59901 confuser lands at the +5.0 s delay
boundary, so even the large retained-bank gap is conditional on the searched
delay window.
