# V3 missing-signal investigation: `cap-20260825T150802-473cb5bbcbd6`

## Conclusion

The apparent V3 loss is primarily an acquisition-adjudication defect, not an
absence of Qin pilot energy and not evidence of periodic physical frame
resets. A rolled Qin sequence is currently used as V3's negative control while
the exact and control templates are each allowed to search the whole frame.
The control can therefore reacquire the same pilot approximately 187 samples
earlier and veto it.

There is one genuinely distinct concurrent CFO family on `stream-1/rx1` early
in the dwell. It may worsen ten missing windows, but 47/57 losses occur without
such overlap. The products are candidate-only and provide no satellite ID, so
the second family cannot be called a second satellite from this capture alone.

The follow-up acquisition-model audit confirms the mechanism on frozen
counterfactuals and develops a seed-aware short-block successor model.  See
`reports/2026_08_25_150802_v3_acquisition_model_audit.md` for the full 537-row
conditional-control replay, the 20 ms block-consensus experiment, null
calibration boundary, and additive V4 recommendation.

## Population and counterfactual

The full-dwell replay contains 57 windows where V2 returns `complete` and V3
returns `no_result`. The net V3 completion deficit is 54 because three other
windows complete only in V3.

- All 57 V2-only windows were rejected by Standard V1.
- None of the 57 qualified V2 modulo-pi phase lock.
- V3 acquisition rejects 48/57 on a negative exact-minus-control margin; the
  other nine acquire a basin but no frame passes the per-frame pilot gate.
- Bypassing V3 acquisition and running the V3 phase-safe Kalman core at the
  persisted nominal V2 epoch/CFO completes 57/57 with the same supported-frame
  counts as V2, but still qualifies phase lock on 0/57.
- Forcing the rejected V3 winner through tracking completes 26/48; the other
  22 contain no supported frame at that selected basin. Including the nine
  post-acquisition failures, 31/57 losses therefore involve an unsupported
  selected basin and 26/57 are pure control vetoes. Neither group contains a
  phase-qualified V2 result.

This means V3 did not erase accepted tracking evidence. It stopped publishing
already-unqualified V2 state estimates.

## The control/epoch alias

V3 uses `symbol_roll=17` as the control sequence. At this sample rate,

\[
17 \times 4.4\,\mu s \times 2.5\,\mathrm{MS/s} = 187\ \mathrm{samples}.
\]

Because the control independently searches all 3,334 integer epoch hypotheses,
it can align to the real Qin sequence at nominal epoch minus 187--188 samples.
The exact template and that shifted control have correlation 0.961. The odd
17-symbol shift also swaps the acquisition/verification even-odd symbol
parity, so the two scores are not independent held-out evidence.

On the 18 strongest vetoes (margin at most -0.05), every control winner is at
nominal minus 187 +/- 1 samples and within 250 Hz of the nominal CFO. Exhaustive
300-roll checks on representative failures put roll 0 first at the nominal
epoch and roll 17 first at the shifted epoch; the next-best roll scores at most
about 0.031. This is structured Qin evidence from the same sequence, not a
random interferer. Paired V3 successes also have a median control/exact ratio
of 0.941, so a zero-margin decision can flip on small candidate-refinement
differences even when the signal is present.

Among the 50 robust losses with 18--56 V2 frequency updates:

- 25 stay within two samples of the nominal epoch but are vetoed by the rolled
  control. Every control winner is at nominal minus 185--188 samples.
- 25 jump by 35--1,557 samples to a diffuse noise basin (median absolute jump
  612 samples, 24 distinct rounded offsets). A direct CFO sweep at the nominal
  epoch recovers exact-Qin score 0.041--0.190 in every one of these 50 windows.

Representative scores are:

| path/time | V3-selected exact | exact at nominal epoch | shifted control |
|---|---:|---:|---:|
| `stream-1/rx1`, 0.175 s | 0.0399 | 0.1610 | 0.1583 |
| `stream-0/rx1`, 21.675 s | 0.0252 | 0.1444 | 0.1319 |
| `stream-1/rx0`, 3.900 s | 0.0247 | 0.0967 | 0.0921 |

An expanded CFO search does not fix this. Only four losses selected the edge of
the original +/-2 kHz search; repeating them at +/-4 and +/-8 kHz recovered no
additional supported tracking. The direct nominal-epoch sweeps also never
selected a CFO boundary.

Candidate retention is the coupled failure. V3 retains eight full-frame basins
per template. Raising that bound to 16 recovers the correct 75 ms alignment in
19/48 global-margin failures; 16 then track and three choose unsupported
basins. A bound of 32 recovers 25/48 alignments. For example, at 0.175 s the
retained exact score changes from 0.0399 to 0.1615 and the margin from -0.0998
to +0.0218. At 3.175 s it changes from 0.0471 to 0.2025 and the margin from
-0.1408 to +0.0146. None of the counterfactual recovered tracks qualifies
phase lock. Increasing the bound is therefore diagnostic mitigation, not a
scientific promotion and not a complete substitute for an independent
control.

## Ordinary CFO aliasing

The expected OFDM discriminator alias spacing is
`1 / 4.4 us = 227,272.727273 Hz`. Seven V2-only rows are trivial wrong-alias
hypotheses: each has only one V2 frequency update and a same-time peer exactly
one alias away. Six of those peers complete V3; the seventh peer has 56 V2
updates but independently suffers the rolled-control defect above.

Same-time multiplicity elsewhere is also dominated by this representation:
47/57 V3-missing rows and 185/263 paired V2/V3 successes have a same-time alias
companion. After reduction modulo the alias period, the median separation of
the missing companions is `2.7e-7 Hz`. Thus visible parallel lines separated
by exactly 227.273 kHz are alias copies, not multiple satellites.

## Concurrent signal candidates

One early interval on `stream-1/rx1` contains two canonical CFO families that
do not collapse under the 227.273 kHz alias:

| candidate family | interval | modulo-alias intercept | local slope |
|---|---|---:|---:|
| A | 0.000--6.400 s | about 84.406 kHz | -3.418 kHz/s |
| B | 0.175--3.075 s, continuing through 9.250 s | about 226 kHz | -3.550 to -3.265 kHz/s |

Their invariant separation over the overlap is about 84.91--85.45 kHz. This
is distinct simultaneous Qin-candidate activity, not an OFDM CFO alias and is
not explained by simple static multipath, which should retain carrier CFO
while changing delay and phase.

It is not the general explanation for V3 loss:

- 10/57 missing windows occur in the distinct-overlap interval; 47/57 do not.
- V3 misses 10/40 V2-complete rows during overlap (25.0%) and 47/280 outside it
  (16.8%). This is suggestive but the windows and alias rows are correlated.
- `stream-1/rx0` has the highest path loss rate, 10/32 (31.2%), despite no
  distinct concurrent canonical track.
- The largest five-second loss bin is 40--45 s and is unrelated to the early
  overlap.

The second family could be another transmitter/beam, another satellite, or a
research-track false positive. There is no payload decode, TLE association, or
frequency-intercept-aware cross-receiver corroboration, so a multiple-satellite
claim is not supported.

## Frame-reset test

The signal is stable inside the missing 75 ms windows. Five representative
early `stream-1/rx1` failures were divided into twelve overlapping 20 ms slices
each (5 ms step) and tightly rescored around the nominal model. All 60/60
slices retain exact-Qin score above 0.1:

| 75 ms window start | exact-score range | capture-relative epoch span | CFO residual |
|---:|---:|---:|---:|
| 0.175 s | 0.176--0.222 | 1.33 samples | 0 to +50 Hz |
| 0.350 s | 0.197--0.234 | <=1 sample | 0 Hz |
| 1.900 s | 0.181--0.226 | 1.33 samples | +/-50 Hz |
| 2.075 s | 0.202--0.256 | 1.67 samples | 0 Hz |
| 3.175 s | 0.194--0.250 | 1.67 samples | +100 to +150 Hz |

Default V3 nevertheless misses the correct basin in these slices. At 0.175 s,
for example, it selects the correct basin in 0/12 slices, moves more than 100
epoch samples in 7/12, and moves more than 500 Hz in 12/12. The strong
persisted 20 ms GLRT evidence is therefore real; the signal neither ends after
the first 20 ms nor resets inside the window.

Across all robust bad-epoch cases, offsets are also diffuse rather than
periodic: 24 distinct rounded offsets among 25 windows, with none clustering at
a frame boundary or at multiples of 187 samples. The other 25 robust losses
retain the nominal epoch. The deterministic minus-187 control displacement is
produced by the template construction, not by a transmitter reset. This replay
finds no evidence of periodic physical frame resets in the missing V3 rows.

## Recommended correction

1. Always retain and evaluate the supplied nominal epoch/CFO basin.
2. Score the negative control at the exact candidate's same epoch and CFO, or
   use a control that cannot become the exact Qin sequence through an epoch
   shift.
3. Revisit the eight-basin retention bound after making the control
   independent; larger bounds recover some correct basins but do not create
   qualified phase lock by themselves.
4. Treat one-update V2 completions as unresolved CFO-alias hypotheses rather
   than recovered tracks.
5. Re-run this frozen full-dwell comparison after correcting the acquisition
   control; do not relax phase-lock qualification to manufacture recoveries.

The relevant implementation independently searches the rolled control in
`src/leo/analysis/starlink/acquisition.py` and invokes that search from the V3
entry point in `src/leo/analysis/qam/pilot_pnt_kalman.py`. No Standard artifact,
golden fixture, or QNAP recording was changed during this investigation.

## Evidence

- [Full-dwell replay data](figures/2026_08_25_150802_v3_full_dwell/full-dwell-results.json)
- [Full-dwell method and coverage](2026_08_25_150802_v3_full_dwell.md)
- Persisted Standard alias maps, dealiased branches, final trajectories, and
  pilot scans under the capture's read-only analysis directory in
  `/srv/bulk/leo/analysis`.
