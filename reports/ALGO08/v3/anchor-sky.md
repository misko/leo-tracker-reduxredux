# Cross-channel orbital proposals from sparse two-scan anchors

On the physical DS30-0016 ledger, a cap of two cross-channel proposals recovered **233 of 694 held factors given exact timing**. With timing estimated from anchors, it recovered **45 of 694 using the target RF's phase** and **29 of 694 using a common phase across RFs**. The subset whose fitted tracklet had only foreign-RF anchor support recovered **26 signed frequencies and zero joint frequency-and-time matches**. The independent southern simulation yielded zero proposals under the same rule. These results rule out a waveform replay of this proposal method at the tested cadence. [Frozen protocol](anchor-sky-protocol.md) · [Measurements](measurements/anchor-sky.json)

## What the predictor knew

The experiment used complete pre-continuation factors from the earlier exact `950c2b94` two-scan receiver. The ledgers bind to the ordered saved detections, recording authority, operator region and terminal digests. The physical archive came from its frozen DS30 request. The simulated archive came from the later installed-v3 receipt on the same raw recording and session. That receipt supplies only the causal archive authority. The older pair supplies the region originally offered to its factor ledger. The predictor saw counters, receiver, edge and actual RF for all admitted visits, and full verified factors for the scheduled 93/713 physical and 152/1,200 southern anchors only. The full outcome ledgers were joined after the prediction digest was fixed. Both prediction digests reproduced exactly in a separate execution. [Runner](anchor_sky.py) · [Previous same-lane census](anchor-orbit-census.md)

The recorded upper and lower UTC bracket endpoints set the midpoint and causal catalogue cutoff. The 48-hour causal policy admitted 11,181 physical and 10,937 simulated catalogue entries before spatial screening. The offered screen and −12° horizon left 1,163 and 1,615 trajectories. Doppler and range were calculated at the operator's offered center. A provisional tracklet had to share a folded orbital frequency residual across three distinct anchor visits on at least two RFs. It could absorb a receiver-specific local frequency offset. Ranking retained 12 candidates per receiver and four-second block and prioritized one likely signed branch per identity. The fitted frequency offset may absorb small receiver drift over those blocks. The fit uses no drift extrapolation beyond that local assumption, no fitted location and no learned `c`. Neither later TLEs nor solver ownership nor true sites enter this test. [Scientific inputs and rank rule](anchor-sky-protocol.md)

Physical blocks admitted 9,955 satellite-and-block matches before the cut to 216. A shared folded residual is weak identity evidence on these short blocks. The 227.27 kHz folding period only helps link candidates. Scoring and the proposed receiver call both require the actual signed CFO. The modal receiver branch can change between channels, while an unseen satellite or carrier can have no fitted tracklet at all. The all-branch oracle reached **310/694** at the fixed shortlist with perfect timing, versus **233/694** at cap two. The residual gap includes unobserved tracklets, shortlist and point-chart failures. These saved factors alone cannot attribute each miss to a specific satellite or alias. [Orbit and branch counts](measurements/anchor-sky.json)

## Antennas, phase and held factors

The physical ledger provided 19 stereo anchor visits with factors on both receivers. Eleven had a pair within 25 kHz after folding by the GLRT period, and none had a pair within 25 kHz in absolute signed frequency. The preregistered raw stereo calibration therefore withheld transfer. The southern case supported a 2.649 kHz stereo offset from 21 modal-bin anchor visits. Under both its separated and pooled receiver models, 126/150 local blocks had fewer than three usable anchor visits. The other 24 had enough visits and distinct RFs, yet had no accepted orbit-residual cluster. The southern result bounds this schedule and model on this simulation. It leaves a wider lookahead or separately calibrated receiver as a different test. [Stereo and opportunity counts](measurements/anchor-sky.json)

The local timing model used two inlier anchors on the same receiver, RF and edge and estimated a wrapped frame-phase secant after removing the estimated range delay. The shared model allowed RF transfer on one receiver. The UTC bracket spanned 133.53 frame periods on DS30-0016 and 7.50 on the simulation. A ±6-sample confirmation window at 10 MS/s permits ±0.6 μs, whereas the TLE has no transmit frame epoch or receiver sample phase. The supplied square's corners differed from center predictions by up to 14.75 kHz and 590 samples of absolute range delay on DS30-0016. The southern maxima were 14.23 kHz and 590 samples. These are maximum deviations across the screened sky. They show the scale of the center-chart restriction rather than error bars for the held factors. The physical and simulated ledgers each pinned one pilot edge. Cross-edge timing remains untested. [Clock, range and timing evidence](measurements/anchor-sky.json)

| Physical cap | Signed proposals, including negatives | Signed hits given exact time | Local-RF phase attempts / joint hits | Shared-RF phase attempts / joint hits |
|---:|---:|---:|---:|---:|
| 0 | 0 | 0 | 0 / 0 | 0 / 0 |
| 1 | 1,240 | 183 | 233 / 38 | 935 / 24 |
| 2 | 2,480 | 233 | 373 / 45 | 1,998 / 29 |
| 4 | 4,960 | 273 | 711 / 52 | 3,686 / 32 |

Each physical held lane received exactly the signed count in its cap. This includes all 762 of 1,240 lanes where the original detector found no factor. At cap two, the local-phase model had 0/1/2 testable proposals on 963/181/96 lanes. The shared-phase model had 0/1/2 on 17/448/775 lanes. Of its 1,998 attempts, 1,969 were unmatched against the verified ledger. Cap four had 15/112/329/220/564 shared-phase lanes with 0/1/2/3/4 attempts. This extra sensitivity only changes how many proposals reach scoring from the same frozen predictions. The southern model had zero proposals on every one of its 2,096 held lanes for each cap. Unmatched counts compare the proposals with the saved factor set. A waveform test could find detections outside that set. [Counts at each cap and by antenna/RF](measurements/anchor-sky.json)

| Physical scoring mode | Held factors / 694 | Held residuals / 216 | Original causal selections reproduced / 440 |
|---|---:|---:|---:|
| Cap two with same-RF timing | 45 | 11 | 28 |
| Cap two with shared timing | 29 | 6 | 20 |
| Cap four with same-RF timing | 52 | 11 | 34 |
| Cap four with shared timing | 32 | 6 | 21 |
| Cap two using foreign-RF support only, shared timing | 0 | 0 | 0 |
| Cap two using foreign-RF support only, perfect timing | 26 | 6 | 11 |
| All shortlisted signed aliases, perfect timing | 310 | 71 | 220 |

The timing oracle selects with knowledge of the held epoch. The alias oracle tries all 105,685 signed cells in the shortlist, with a median 84 and maximum 96 per physical held lane. In each proposal arm with estimated phase, the original causal continuation reran on the evidence retained by the ±2,250 Hz and ±6-sample match. A digest-pinned packet for raw visits 0–47 preserves the mixed-RF model's signed frequency and timing proposals. It retains five rejected raw visits and exposes neither held factors nor satellite IDs. Its selection used visit order alone. [Opaque diagnostic packet](measurements/anchor-sky-DS30-0016-development-packet.json) · [Verification receipts and digest](measurements/anchor-sky.json)

## CPU implications

Catalogue read, projection and proposal generation cost **2.996 CPU s** on the 35.7-second physical capture and **2.272 CPU s** on the 298.3-second simulation. The original native anchor detector calls alone cost 0.615 and 0.817 seconds. The best physical cap-two timing model still needs 3.179 native CPU seconds for anchors and full retries on lanes with missed saved factors, given free recognition of empty lanes. Including the unchanged 1.962 acquisition CPU seconds outside the native callbacks leaves an optimistic 5.141 of the original 6.592 seconds before model or confirmation costs. Charging 373 original-waveform attempts at the earlier 0.94 ms per verifier call adds 0.351 seconds. Including the observed model generation raises this illustrative total to 8.49 seconds. Shared-RF timing had 1,998 attempts, costing about 1.878 seconds at the same reference rate. [CPU inputs and calculation](measurements/anchor-sky.json) · [Verifier timing reference](../single-core-2x/receiver-coarse-bank.md)

The dense installed-v3 callback audit measured **4.594 CPU seconds for the scheduled anchors**. Even with 2× solving and zero publication cost, the dense CPU allowance is **0.529 ms per originally selected non-anchor factor**, or about 3.26 seconds. The warmer elapsed transfer allows **0.766 ms**, or about 4.73 seconds. A single old verifier call per 6,170 originally selected non-anchor factors already costs about 5.80 seconds. Extrapolating the measured physical cap-two shared-phase attempt rate to all 11,834 dense held receiver lanes would cost about 17.9 seconds at that verifier rate, including proposals that fail on the true waveform. The extrapolation assumes the DS30-0016 attempt rate transfers and grants no validation of DS30-0008 recall. [Measured dense acquisition split](https://github.com/misko/leo-tracker-reduxredux/blob/7146070824b07bc3589e99d1318171fcfa3afc2e/reports/ALGO08/v3/acquisition-split.md)

The model uses both earlier and later anchors around each four-second block. In ordinary receiver-separated fitting this can require up to ten seconds of lookahead from a block edge. The pooled stereo offset was estimated over the recording's anchor visits. The study timed saved numerics without raw buffering, rereading, verification, localization or publication. The proposal method provides too little joint recall and too many negative attempts to advance to those stages. [Original storage ceiling](anchor-orbit-census.md)

## Reproduction

```sh
bench=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
lock() {
  flock -x "$bench/gauss.lock" nice -n15 ionice -c2 -n7 taskset -c 2 timeout 25s \
    env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH="$PWD:$PWD/src" \
    "$tree/.venv/bin/python" -BPs "$@"
}
lock -m reports.ALGO08.v3.anchor_sky "$bench/integration-shared/pairs/DS30-0016/pair.json" \
  "$bench/ledger-DS30-0016.json.gz" \
  /srv/bulk/leo-dev/ds30-full-20261121/snapshot/inputs/DS30-0016/request.json \
  "$physical_predictions" "$physical_receipt" --preview "$development_packet"
lock -m reports.ALGO08.v3.anchor_sky "$bench/integration-shared/pairs/south/pair.json" \
  "$bench/ledger-south.json.gz" "$bench/exact-curved-lookahead-south-inside/pair.json" \
  "$south_predictions" "$south_receipt"
lock -m pytest -q tests/pipeline_eval/test_anchor_sky.py tests/pipeline_eval/test_anchor_orbit_census.py
```
