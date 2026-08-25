# Catalogue-screened raw satellite activity: 073628 and 085623

## Outcome

The raw duration model now starts from the complete persisted bounded
`PilotScanV3` peak prefix and performs an unseeded Starlink catalogue screen.
It rediscovers the leading independently proposed TLE candidate in two signal
dwells:

- `073628`: NORAD 58636 / STARLINK-31008 ranks first and is the only satellite
  selected by the grouped activity solver.
- `085623`: NORAD 58610 / STARLINK-31089 ranks first and is the only satellite
  selected by the grouped activity solver.

This is convincing evidence that the prototype can recover a satellite-shaped
frequency trajectory without being handed the winning NORAD. It is not a
spacecraft identification, a payload decode, or a solved unrestricted satellite-count problem.

A later three-path/cross-band dwell independently exercises the new shared-mask
multipath solver and selects NORAD 66811 from a supplied three-object bank; see
the [103607 report](2026_08_25_103607_raw_satellite_activity.md). It is kept
separate because its wider delay study and shortlist were chosen post hoc.

## Frozen inputs and model

- Detector-score calibration:
  [`score-calibration-v3.json`](figures/2026_08_25_raw_satellite_activity_calibration/score-calibration-v3.json)
- `073628` raw extraction:
  [`capture-input.json`](figures/2026_08_25_073628_satellite_activity/capture-input.json)
- `073628` exhaustive-fine catalogue replay:
  [`raw-catalogue-37p5-60-score-v3-exhaustive-fine.json`](figures/2026_08_25_073628_satellite_activity/raw-catalogue-37p5-60-score-v3-exhaustive-fine.json)
- `085623` raw extraction:
  [`capture-input-5d4d-rx0.json`](figures/2026_08_25_085623_satellite_activity/capture-input-5d4d-rx0.json)
- `085623` staged catalogue replay:
  [`raw-catalogue-52p5-60-score-v3.json`](figures/2026_08_25_085623_satellite_activity/raw-catalogue-52p5-60-score-v3.json)
- Other `085623` receiver-path replays:
  [`5d4d/RX1`](figures/2026_08_25_085623_satellite_activity/raw-catalogue-52p5-60-5d4d-rx1-score-v3.json),
  [`19f2/RX0`](figures/2026_08_25_085623_satellite_activity/raw-catalogue-52p5-60-19f2-rx0-score-v3.json),
  [`19f2/RX1`](figures/2026_08_25_085623_satellite_activity/raw-catalogue-52p5-60-19f2-rx1-score-v3.json)
- `085623` four-path shared-activity replay:
  [`raw-multipath-catalogue-utc-52p5-60-score-v3.json`](figures/2026_08_25_085623_satellite_activity/raw-multipath-catalogue-utc-52p5-60-score-v3.json)
- Hard-null certificate:
  [`holdout-null-062228-5d4d-rx1-raw-catalogue-v1.json`](figures/2026_08_25_raw_satellite_activity_calibration/holdout-null-062228-5d4d-rx1-raw-catalogue-v1.json)
- Two clean-null certificates:
  [`082330`](figures/2026_08_25_structural_penalty_calibration/raw-catalogue-null-082330-19f2-rx0-v1.json),
  [`084200`](figures/2026_08_25_structural_penalty_calibration/raw-catalogue-null-084200-19f2-rx0-v1.json)

The activity lattice uses 100 ms cells and a hard five-cell minimum run. Each
selected catalogue object has one orbital-time delay and one CFO offset shared
across all of its episodes. The current structural costs are 5.25 once per
satellite and 5.75 per episode start; these remain provisional.

V3 detector calibration groups candidates within one sample and 500 Hz before
scoring them. It uses four minimum-rank buckets, worst-source exact Poisson
upper null intensities from eight disjoint null paths, and simultaneous Wilson
lower signal-mark probabilities from one disjoint signal component. The frozen
inventories contain 9 positive groups among 183,213 null groups and 1,627
positive groups in the source-conditioned signal calibration component.
These are conservative marked-point-process pseudo-costs, not posterior odds.

## Unseeded `073628` result

The replay covers `[37.5, 60.0)` s: 900 scheduled probes and 9,000 returned
candidate rows. Resolution grouping produces 7,682 exclusion groups; 1,036
above-threshold groups are modeled. Every probe reaches the ten-candidate
acquisition cap, so this is the complete persisted bounded prefix, not a
physically exhaustive peak inventory.

The frozen TLE file contains 10,972 unique catalogue objects. Over the full
probe-by-delay bank, 444 objects remain strictly above the horizon mask. The
screen evaluates all 444 on delays `-2.0,-1.5,...,+2.0` s, then this audit also
refines all 444 on the 0.1 s grid with two data-proposed CFO modes per delay:
36,408 fine states in total.

The leading zero-satellite-cost single-object scores are:

| Rank | NORAD | Name | Best delay | Delta from clutter null |
|---:|---:|---|---:|---:|
| 1 | 58636 | STARLINK-31008 | +0.2 s | -1194.28 |
| 2 | 58093 | STARLINK-30578 | +0.7 s | -292.45 |
| 3 | 62995 | STARLINK-32819 | +2.0 s | -278.30 |

The default 32-catalogue refinement produces the same top three, the same
grouped selected set, and the same objective as the exhaustive-fine audit.
Thus the coarse grid has complete top-three recall on this dwell.

The exact grouped solve over those three catalogues and four retained states
per catalogue selects only NORAD 58636. Its fitted nuisance state is delay
`+0.2 s` and CFO offset `+437,716.33 Hz`. It uses three legal activity runs:

- `[39.7, 41.5)` s;
- `[41.9, 42.8)` s;
- `[43.0, 60.0)` s.

There are 547 matched probes and 241 active-probe misses. The total objective
improves on the raw-clutter null by 1189.03 pseudo-cost units after paying the
satellite, three episode, and delay-prior costs; selected-assignment residual
RMS is 126.21 Hz. The delay is a nuisance fit,
not a measured orbital-time correction; nearby delay/CFO combinations remain
strongly confounded on this short arc.

## Independent `085623` result

The same unseeded procedure was applied to stream 0 / `radio_pluto_5d4d` / RX0
over `[52.5, 60.0)` s. This window has 300 probes, 3,000 returned candidates,
274 modeled positive exclusion groups, and 441 full-window-visible Starlinks.

The fine shortlist is NORADs 58610, 62139, and 63110. Their best zero-satellite-
cost deltas are -876.64, -829.76, and -821.19 respectively. The exact grouped
solve selects only NORAD 58610, with delay `-0.1 s`, CFO offset
`+380,840.38 Hz`, one legal `[52.5,60.0)` episode, 273 assignments, 27 misses,
and total delta -871.39. Selected-assignment residual RMS is 47.21 Hz. Because
the modeled interval fills the analyzed window while boundary censoring is
disabled, it does not measure the physical transmission onset or duration.

A separate audit refined all 441 eligible objects on the fine grid and returned
the same top three, selected catalogue, and objective as the default 32-object
refinement.

This independently agrees with the separate four-path/cross-band rate-shape
analysis that proposed NORAD 58610. The catalogue gap is much smaller than in
`073628`, and wrong-time alternatives remain nontrivial, so the result is a
useful association witness rather than identity evidence.

### Independent path check

Running the same unseeded screen separately on the other three receiver paths
does not produce four unanimous votes, which is scientifically useful:

- `19f2/RX1`, the other dense path, independently selects NORAD 58610 with
  delta -951.53, 295 assignments, five misses, and a `+0.2 s` delay nuisance;
- `5d4d/RX1` is weak and nearly tied: NORAD 62139 wins with delta -24.76, while
  the zero-satellite-cost scores for 62139 and 58610 are -30.01 and -29.73;
- sparse `19f2/RX0` selects nothing. Its pruned screen is inconclusive rather
  than a global null certificate.

Thus two independently dense raw inventories recover NORAD 58610, one weak
path cannot distinguish it from the runner-up, and one sparse path contributes
no standalone association. A proper multipath model should share activity and
orbital delay while fitting a separate CFO constant per receiver path; it
should not turn these four outcomes into an unweighted vote.

### Joint four-path check

The four paths were subsequently placed on one absolute-UTC 100 ms grid and
decoded together over the explicit shortlist 58610, 62139, and 63110. Each
catalogue retained four nuisance states, and the exact fixed-state solver
evaluated all 64 joint combinations. It selects only NORAD 58610, with a shared
delay of `-0.2 s`, one full-window 7.3 s activity run, and a total delta of
-1380.88 from the raw-clutter null.

The evidence is deliberately not reduced to receiver votes. Assignment/miss
counts are 265/27 on 5d4d/RX0 and 287/5 on 19f2/RX1, but only 68/224 on
5d4d/RX1 and 25/267 on 19f2/RX0. The two sparse paths therefore contribute
positive local costs of +90.95 and +307.45 rather than being silently dropped;
the two dense paths overcome them with -854.99 and -935.37. Per-path constant
CFO offsets are fitted independently while the activity mask and delay are
shared.

This is a convincing conditional activation witness, not a global identity
solution. The full-window run does not measure onset, the three-catalogue
shortlist and four-state banks are pruned, and requiring a transmitter on every
usable probe of every path is a strong occupancy assumption. It is appropriate
for this simultaneous event but still needs an explicit path-by-cell band
eligibility state before general cross-band use. The leading retained NORAD
63110 confuser is still improving at the `-2.0 s` delay-grid boundary, so the
reported shortlist gap is conditional on that searched delay window.

## Null certificates

Before propagating a catalogue, the new tool evaluates an optimistic global
lower bound: every hypothetical satellite is granted zero residual error, the
best available candidate at each probe, zero delay-prior cost, and even relaxed
cross-satellite reuse of candidate groups. The real objective cannot do better.
If that relaxed five-cell semi-Markov model still chooses the null, no catalogue
object and no number of additive satellite schedules can beat the null.

The certificate returns `N=0` for:

- `062228` 5d4d/RX1, despite 39 modeled above-threshold groups;
- `082330` 19f2/RX0, with zero modeled positive groups;
- `084200` 19f2/RX0, with zero modeled positive groups.

This corrects the old pooled-score replay that falsely activated the hard null.
It does not yet calibrate a false-activation rate: these are only three
analyzer-selected empirical controls, not ground-truth satellite absence.

## Interpretation and remaining gates

The prototype now demonstrates native-cadence raw-peak association, 0.5 s
minimum episodes, one-time satellite penalties, shared delay/CFO nuisance state,
global exclusion of detector-resolution groups, an unseeded catalogue screen,
and an exact null certificate under the current additive objective.

The result is still conditional in several important ways:

1. CFO modes are data proposed and the grouped solve sees only the top three
   catalogue objects and four retained states each, so unrestricted `N` and the
   global joint optimum are not solved.
2. Rise/set objects are excluded because the current hypothesis lacks a
   per-probe visibility mask.
3. Persisted raw products have no authoritative physical alias-family ID;
   nonidentical integer aliases can still inflate satellite count.
4. Every evaluated probe saturates the acquisition prefix at ten candidates.
5. Satellite and episode costs need dwell-cluster calibration on the same full
   search path. A locked set of at least 59 independent null dwells is needed
   before zero activations can support a one-sided 95% false-activation bound
   below 5%.
6. Multi-receiver fusion should share one delay and activity mask while keeping
   a separate CFO offset per path. On the current short tails, delay remains
   intercept-confounded and must be reported as prior-driven.
7. Payload decode, capture-bound observer authority, fresher orbital elements,
   and repeated-pass or second-station confirmation remain the strongest paths
   to spacecraft identity.
