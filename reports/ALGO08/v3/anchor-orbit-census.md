# Sparse anchors for waveform acquisition

A sparse, two-sided **same-lane** proposal route falls short of the ALGO08v3 target. Even when the oracle identifies empty lanes for free, verifies the correct proposals at zero cost and runs the original detector wherever a factor would be lost, acquisition still costs about 63% of baseline CPU on two saved factor ledgers. The warm dense publication would allow only **0.633 ms per non-anchor selected factor** for waveform verification and all other model and search work, even if a perfect recording-wide predictor supplied every correct proposal. These results stop the current design at the saved-ledger census. [Prespecified protocol](anchor-orbit-census-protocol.md) · [Measured receipt](measurements/anchor-orbit-census.json)

## Two-sided support

Take one randomly selected full stereo anchor per eight admitted visits of each exact RF, channel and pilot edge, with the full detected factor list on each antenna. The schedule uses the fixed seed 8011 and visit metadata. Give each intervening lane every compatible anchor factor pair within eight seconds on each side, including pairs across intervening empty visits and across scan ranks. The envelope admits the inherited phase and signed-CFO secants, broad curvature, and original full-rate confirmation tolerances. When many cells overlap, the oracle may choose the two that cover the actual independently verified factors. It also recognizes every true empty. A second oracle supplies the exact current timing and needs only a signed-CFO cell. [Protocol and numerical bounds](anchor-orbit-census-protocol.md)

Both complete pre-continuation ledgers reproduce their saved ordered selections through released continuation. The experiment exposes held-out factors only to score availability and replay continuation. It neither estimates an orbit nor uses the final owners, position or scoring site. The earlier strict adjacent-bracket method could cover only 12 of 72 bracketed factors on its physical prefix. Previous past-only tracking lost unexpected factors and continued selections. The older native orbit-anchor work began **after** GLRT and Graph track preparation, retaining about half the observations and dropping 11 of 119 roof fixes relative to the matched joint receiver. It did not replace the waveform scout. [Bracket audit](../single-core-2x/receiver-brackets.md) · [Causal tracking](../single-core-2x/receiver-tracking.md) · [Historical orbit-anchor analysis](../../2026_11_19_receiver_screening/refinement/anchor-full/README.md)

| Complete factor ledger | Full stereo anchors / visits | Non-anchor factor coverage, CFO and phase / perfect timing | Non-anchor residual coverage, CFO and phase / perfect timing | Exact same causal selections, CFO and phase / perfect timing |
|---|---:|---:|---:|---:|
| DS30-0016 physical | 93 / 713 | 309 / 694 · 326 / 694 | 101 / 216 · 108 / 216 | 203 / 440 · 220 / 440 |
| Southern public simulation | 152 / 1,200 | 74 / 463 · 74 / 463 | 0 / 0 | 44 / 456 · 44 / 456 |

The two-coordinate oracle yields 18 new or changed physical selections because smaller factor histories change later preferences. It yields 221 physical and 44 simulated selections overall. Anchor-only evidence produces zero selections under released chronological continuation on both ledgers. On 280 of 1,240 physical non-anchor lanes the envelope admits more than two anchor pairings, even before checking phase branches. A real two-proposal ranking would need additional evidence to select the useful cells. The simulated cadence leaves only 74 non-anchor lanes with even one admissible pairing.

The whole-recording installed-v3 DS30-0008 and DS30-0374 documents contain **already selected** factors. They omit unselected full anchor factors and possible continuations of other candidates. As a scoring-only sensitivity check, the selected streams retain respectively 2,495 of 7,016 and 1,743 of 4,157 exact baseline selections under the two-coordinate oracle. Granting perfect timing raises those counts to 2,785 and 1,913. Of 399 and 174 previously selected non-anchor residuals, the corresponding perfect-timing sensitivity covers 114 and 59. These counts neither bound all possible cross-channel orbital proposals nor support a position result. The separate matched v3 solver witnesses used 4,472 and 2,905 associated measurements in each calibration arm. Even if every exact selection in this proxy were among those associations, the two-coordinate proxy could supply only 56% and 60% of those original measurements. [Saved solution evidence and clock boundaries](../single-core-2x/regional-doppler-envelope.md) · [Recorded selected-stream scores](measurements/anchor-orbit-census.json)

The earlier scheduled burst still verified all raw windows but yielded only 144 of 456 post-continuation factors on northern simulated input and withheld both positions. Fewer detections and a lower frequency residual do not establish better localization. Any future waveform design that passes the acquisition screen would need a paired position test in independent containing and omitted offers, keeping observations, candidate sets and search budgets fixed for the `c = 0` and fitted-`c` comparison. [Cadence and both calibration decisions](../single-core-2x/cadence.md)

## Cost ceiling

Charge the original measured native CPU for full anchors and every lane on which even the perfect-timing oracle would lose a factor. Other native calls, original-sample verification, candidate generation and empty classification are free in this estimate. The physical ledger still costs **2.186/4.631 native CPU seconds**, and the simulation **2.881/6.357**. Adding their observed non-native acquisition CPU gives **4.147/6.592 s (62.9%)** and **5.945/9.422 s (63.1%)**. The numerators are optimistic CPU estimates and the denominators are measured acquisition CPU before any solver work. These two ledgers used the older exact `950c2b94` receiver.

For the installed v3 warm dense publication, halving solving and retaining the 3.34-second publication tail leaves **24.68 seconds** of acquisition elapsed. The full acquisition measured 52.70 elapsed seconds. Using the approximately 36.5 receiver CPU seconds projected from resident calls leaves about 16.20 seconds for verified input, waits and other acquisition work. With that cost fixed and anchoring 848/6,765 stereo visits at the same mean native cost, the anchor detector adds 4.58 seconds. Perfect proposals on all other lanes now leave **3.90 seconds for 6,170 already selected non-anchor factors**, or **0.633 ms per selected factor**. The budget also has to cover all additional verified but unselected factors, candidate misses, negative waveform tests, model fitting and scheduling. An earlier cost profile of the full independent verifier averaged about 0.94 ms per reached call. The later exact-score repair alone averaged 0.541 ms in a chronological prefix, after paying for proposal generation and a separate eligibility check. Those different-lineage clocks are engineering scale comparisons. They supply no measured receiver with enough headroom at 0.633 ms. [Installed stage clocks](first-55/stage-clocks.csv) · [Native budget analysis](receiver-polyphase-timing.md) · [Earlier verifier profile](../single-core-2x/receiver-coarse-bank.md) · [Exact-score repair timing](../single-core-2x/receiver-fractional-absolute-score.md)

Anchor locations span the recording. A model built from all anchors first would need to retain about **9.47 GB** of pending decoded stereo I/Q on dense DS30-0008, excluding overhead and anchor workspaces. It could also spill and reread that volume, or traverse the compressed recording again. The existing dense publication charged roughly 8.18 GB of compressed input pages, and the integrity checks require valid compressed and decoded-chunk digests and each window digest. A second compressed traversal can reuse trusted metadata but still incurs reads and decode work. A local buffer through only the next same-RF anchor would peak at 70 pending stereo windows, **112 MB**, and 5.31 seconds of lookahead on this same schedule. It does not provide the final recording-wide model at the buffered visit and counts neither raw decoder buffers nor extra retention for a farther useful anchor. [Dense input residency and seal](bounds-physical-pair.md) · [Verified reader costs](../single-core-2x/receiver-ingress.md)

No waveform or orbital inference ran. A different receiver that predicts and confirms substantially faster, finds carriers without a same-RF two-sided witness, and fits inside a bounded one-pass reader remains a separate hypothesis. The current search and exact-verifier budget do not justify more replay.

## Reproduce

```sh
bench=/tmp/leo-algo08v2-2x-bench
pub=/srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac
tree=/home/mouse9911/gits/leo-tracker-reduxredux
release=/opt/leo-algo08/current
lock() {
  flock -x "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 timeout 25s \
    env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="$PWD:$PWD/src:$release/src:$release" "$tree/.venv/bin/python" -BPs "$@"
}
lock -m reports.ALGO08.v3.anchor_orbit_census \
  --ledger DS30-0016 "$bench/ledger-DS30-0016.json.gz" \
    "$bench"/integration-shared/pairs/DS30-0016/candidate/fast-scan-automatic-work/*/detections.json \
  --ledger south "$bench/ledger-south.json.gz" \
    "$bench"/integration-shared/pairs/south/candidate/fast-scan-automatic-work/*/detections.json \
  --selected DS30-0008 "$pub"/v3-bounds-DS30-0008-pair/baseline/fast-scan-automatic-work/*/detections.json \
  --selected DS30-0374 "$pub"/v3-successor-DS30-0374-20261123-pair/baseline/fast-scan-automatic-work/*/detections.json \
  --clocks reports/ALGO08/v3/first-55/stage-clocks.csv
lock -m pytest -q tests/pipeline_eval/test_anchor_orbit_census.py \
  tests/pipeline_eval/test_experimental_receiver_brackets.py
```

The six component tests passed and cover stereo scheduling, wrapped phase, signed frequency, missing residuals and storage accounting, alongside the older strict-bracket controls.
