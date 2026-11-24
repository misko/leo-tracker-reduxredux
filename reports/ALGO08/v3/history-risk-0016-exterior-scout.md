# A wider exterior scout on the physical DS30-0016 omission

The frozen eight-point scout **failed its bilateral screen**. After adding the wider points, receiver 1 kept its original maximum 37.5 km north of the offer centre. Receiver 2 switched to a point 100 km east. Their maxima were **102.133 km apart**, over the predeclared 25 km limit. A separately scored reference point beat all 104 scheduled points for both radios. This shows the saved evidence can favour the site when the scorer is given its location. It gives no way to nominate that location before scoring and leaves the signed false fix unchanged. The science screen failed, so the trial stopped after this one offer. [Frozen protocol](history-risk-0016-exterior-audit.md) · [Full receipt](measurements/history-risk-0016-exterior-scout.json.gz)

## Independent receiver scores

Gains below are against each receiver's best point on the unchanged inside lattice. Coordinates are east and north in kilometres relative to the original omitted offer. Each reported exterior maximum was unique. Wider-only maxima are descriptive and use the original inside comparison.

| Point set | RX1 best exterior | RX1 gain | RX2 best exterior | RX2 gain | Separation |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original 48 exterior | (+5, +37.5) | +0.07494 | (0, +62.5) | +0.16712 | 25.495 km |
| Original plus 8 | (+5, +37.5) | +0.07494 | (+100, 0) | +0.24892 | 102.133 km |
| Wider eight only | (−200, 0) | +0.00424 | (+100, 0) | +0.24892 | 300.000 km |
| Known site, post-seal single-point diagnostic | (−170.464, −6.321) | +0.24992 | (−170.464, −6.321) | +0.36525 | Single point |

The −200 km west point was the only added point with positive gain for both radios (+0.00424 and +0.19392) and was 30.205 km from the reference. RX1's gain there did not beat its original outside maximum. RX2's best wide point was east of the offer. Scoring the actual site increased the maxima over the entire 104-point schedule by **+0.17498 / +0.11633** for RX1 / RX2. The original full 96-point decision reproduced the archived terminal Boolean. Its two maxima exceeded the gate separation by 0.495 km. Nothing in the experiment changed the original short-circuit or introduced a withholding decision. [Sealed physical publication](history-risk-0016-omitted.md)

## Graph support and catalogue stages

| Stage | Original 96 | Eight wider points | Site diagnostic |
| --- | ---: | ---: | ---: |
| Causal catalogue | 11,181 | 11,181 | 11,181 |
| First propagation | 11,180 | 11,180 | 11,180 |
| Horizon envelope candidates | 554 | 658 | 637 |
| Usable after full propagation | 554 | 658 | 637 |

The same **301 of 506** signed observations supported all three score banks. RX1 retained 215 of 318 points in eight tracks and RX2 retained 86 of 188 in four tracks. The full 318 and 188 still supplied the respective receiver denominators. The receipt records exact observation and track memberships, stage NORAD lists and a big-endian visibility bitmap per track and point indexed by that bank's usable NORAD list. Doppler likelihood uses the installed signed within-track contrast, original phase prior and full-catalogue weight. A constant offset at a track's fixed RF cancels from this contrast. The previous false published fixes were 183.656 km wrong with c = 0 and 176.717 km with fitted c. This scout generated no new position, RF residual, grid or figures. [Installed scorer source](../../../tools/pipeline_eval/variants/experimental/regional_reassignment.py)

Only after the blind seal did the worker inspect the earlier containing owners and the site reference. Both containing-owner families, 63510 and 64015, survived the three geometric stages in every bank, passed time visibility on every one of the 12 tracks at all 105 locations, and received likelihood evaluations. Neither led an RX2 track at the reference. They led four of eight RX1 tracks there and the other families also contributed. This rules out either of these families being skipped by the catalogue or time visibility filters in this case. The large Graph losses, especially for RX2, remain an independent limitation. The strongest sampled points and the reference show how the same available evidence responds at different locations. They leave the effect of restoring discarded observations unmeasured. [Reference-linked likelihood terms and masked support](measurements/history-risk-0016-exterior-scout.json.gz)

## Paid cost and stopping decision

The saved-only worker exited 0 in **2.89 s elapsed**, **2.78 s user + 0.11 s system CPU**. It scored 104 scheduled points and the one post-seal reference below the 3.5 CPU-second cap. It used the shared Gauss lock, CPU 2, nice 15, best-effort I/O priority 7 and one numeric thread. The 46 admitted archive extents totalled 82,259,111 bytes on resident tmpfs. The actual causal selection reread and verified 32 snapshots or 57,215,035 bytes through its existing reader. The process reported zero filesystem input blocks and zero major faults. No backing waveform, raw acquisition, RF collection or position solver ran.

| Paid slice | CPU s |
| --- | ---: |
| Startup and admission through pinned saved packet and archive extent checks | 0.156 |
| Original Graph preparation | 0.077 |
| Verified causal catalogue construction | 1.432 |
| Original projection bank and first 24 terminal scores | 0.288 |
| Remaining 72 original scores for telemetry | 0.607 |
| Wider bank projection and eight scores | 0.165 |

The marginal eight-point step cost **17% of the 0.96 s remaining speed gap** when given the already prepared Graph and catalogue. Charging the completed original lattice as well raises that increment to **0.772 CPU s** (80% of the gap). This is stage arithmetic on one saved physical offer. An integrated end-to-end runtime change was unmeasured. A first startup exited before scientific admission because an import expected a research qualification module in the installed namespace. It took **0.15 s wall / 0.14 CPU s**, scored zero points and did no waveform or archive reads. The archive port import was corrected and dry-tested before the only scoring process. Thirty component checks passed. The frozen criterion failed on the scheduled points, so there was no further sweep, radius adjustment or transfer control. [Scout and exact time cap](history_risk_0016_exterior_scout.py) · [Component tests](../../../tests/pipeline_eval/test_history_risk_0016_exterior_scout.py)

To reproduce on the same Gauss staging paths, use a fresh output name.

```sh
flock -w 35 -x /tmp/leo-algo08v2-2x-bench/gauss.lock sudo -n -u leo \
  taskset -c 2 nice -n 15 ionice -c 2 -n 7 \
  env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  /usr/bin/time -v /usr/bin/timeout --kill-after=1s 15s \
  /opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/venv/bin/python -IB \
  /var/tmp/leo-v3-history-risk-0016-raw/reports/ALGO08/v3/history_risk_0016_exterior_scout.py \
  /dev/shm/leo-v3-history-risk-0016-exterior-scout-new
```
