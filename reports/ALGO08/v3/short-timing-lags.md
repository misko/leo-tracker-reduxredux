# One or two current-window timing lags before signed carrier search

A single full-aperture lag reduced native dense CPU from **116.22 to 88.20 ms**, but lost **7 of 44 published dense factors** and **6 of 36 weak mixed factors**. Two lags and four timing rows lost **5 of 44 dense** and **4 of 36 weak** published factors. Complete reruns on exactly the changed dense lanes would leave **2.99 or 2.89 CPU s** of projected savings, falling short of the **3.49 s** dense target. With perfect recognition immediately after the single-lag search, a narrow **3.67 s** ceiling remains. The experiment measured the proposal and priced the answer-key routes. A current-window rule that reliably recognizes those lanes remains open. [Native receipts](measurements/short-timing-lags.json.gz) · [Timing-only oracle](timing-only-oracle.md)

## Fixed scout and scientific boundary

The scout uses the original quarter-rate samples, FIR, full 20 or 12 ms aperture, and both independently estimated modes per antenna. It evaluates only lag **28** or lags **28 and 44** on the full timing grid. A template-only contrast screen ranks one- or two-lag combinations by their worst main-peak-to-sidelobe power ratio. It uses each pinned pilot and five signed CFOs between −750 and +750 kHz, with the original FIR. The best single lag has contrast 62.09 and the best pair has contrast 63.25 across those ideal cases. No saved lane influenced the choice. The candidate passes four or eight timing peaks to the original two-mode signed carrier search. Native refinement, independent pilot confirmation, signed CI16 cancellation on reached anchor scouts and exact fractional verification keep their original arithmetic. Short primary calls remain primary-only. No antenna or history authorizes another's candidates.

Eight lag pairs of forward and inverse FFTs fall to one or two pairs. Four timing peaks take eight full 4,096-bin carrier transforms, compared with the original 24; eight timing peaks take 16. The rejected full-aperture differential fold instead replaced both principal modes with folded lag evidence and estimated CFO from lag phases. The four-frame shortlist changed frame preparation. This study only reduces the number of original lag channels and carrier rows. [Earlier differential scout](differential-fold.md) · [Frame-pair shortlist](frame-block-shortlist.md) · [Masked native scout](short_timing_lags.py)

## Exact packet and candidate results

The 96 dense lanes use the original 16 full and 80 short calls. The saved weak challenges issue 24 full and 12 short calls under their sparse clip chronology. The control relinks both pinned binaries and compares all original factor bytes with the matched local PGO control. All 44 dense selected tuples and all 52 empty rows join exactly to the released mixed detector packet. The mixed lane publishes the strongest verified margin. The counts below give tolerant factor identity within two wrapped samples and 250 Hz of signed CFO at the same scan rank, as well as exact change in the ordered output and chosen factor. No position solve, raw recording replay through publication, or RF collection ran.

| Scope and arm | Native CPU, ms | Timing estimator, µs per reached scout | Changed ordered lane bytes | Changed published lane | Missing / added verified factors | Published factors missing |
|---|---:|---:|---:|---:|---:|---:|
| Dense control | 116.22 | | 0 | 0 | 0 / 0 | 0 / 44 |
| Dense one lag, four rows | 88.20 | 22.0 | 7 | 7 | 7 / 1 | 7 / 44 |
| Dense two lags, four rows | 91.22 | 39.3 | 5 | 5 | 5 / 2 | 5 / 44 |
| Dense two lags, eight rows | 97.59 | 41.7 | 5 | 5 | 5 / 2 | 5 / 44 |
| Weak control | 99.20 | | 0 | 0 | 0 / 0 | 0 / 36 |
| Weak one lag, four rows | 73.69 | 22.7 | 9 | 6 | 10 / 1 | 6 / 36 |
| Weak two lags, four rows | 77.13 | 40.7 | 6 | 4 | 7 / 0 | 4 / 36 |
| Weak two lags, eight rows | 83.31 | 43.0 | 5 | 3 | 5 / 0 | 3 / 36 |

All three scouts missed the dense visit 14 lane 0 primary with exact-minus-rolled margin **0.192** and the DS26-0237 visit 2268 lane 1 primary with margin **0.227**. On the dense slice, all publication differences came from the scheduled 12 ms path. The 25 reached dense full scouts retained every factor, while the weak full anchors exposed dropped residual factors and primaries. Savings on changed lanes can include confirmation and verification that the candidate fails to reach.

## Costs at the dense acquisition boundary

The estimates scale the aperture-specific median CPU ratios by the previously measured 12.635 short and 4.716 full native CPU seconds. The late-retry answer key pays the complete candidate plus a full retry on each changed published tuple. The early answer key pays the measured short timing estimator and the original path on changed tuples, with the original input, FIR and modes shared. It charges no classifier or dispatch cost. Neither answer key has access to this information in the real receiver. The results concern the native stage and leave verified input and the solver untouched. [Dense acquisition requirement](warm-recording-budget.md) · [Measured whole-recording aperture costs](dense-full-short-raw.md)

| Route | Gross candidate saving | With perfect retry after verification | With perfect routing after timing only |
|---|---:|---:|---:|
| One lag, four rows | 4.36 s | 2.99 s | 3.67 s |
| Two lags, four rows | 3.88 s | 2.89 s | 3.45 s |
| Two lags, eight rows | 2.91 s | 1.92 s | 2.54 s |

One lag and four rows leave about **13 µs per full-recording lane** for an early decision, additional candidate ordering and any mistakes under the 3.49 s model. The four-row timing oracle allowed 74 µs per lane, and the eight-row oracle 24 µs. The two-lag estimator alone already exceeds that eight-row allowance at the measured per-scout rates. At this budget the evidence does not support deploying a reduced-lag arm or a retry based on the measured margin alone.

## Prior and peer misses by published outcome

The timing-only audit nominated 370 distinct phase rows across the dense lane scans. Joining the same waveform and original RF, sample clock and antenna to all 13,530 sealed probe records identifies 44 published factors and 52 empty lanes in the test. Each verified factor matches a nearby original quarter-rate nomination within seven native samples at its original scan rank. The other nominees distinguish cells that did not lead to that lane's chosen or second verified factor. The donor set and window geometry use the exact frame wrap and latest two qualified same-radio opportunities within two seconds, plus the simultaneous peer granted for free. This classification uses packet outcomes only afterward. [Timing oracle and drift rules](timing-only-oracle.md#prior-and-peer-timing)

| Original timing-row class | Total | Misses at ±4 samples | Misses at ±64 samples | Misses at ±256 samples | Misses at ±1,024 samples |
|---|---:|---:|---:|---:|---:|
| Published factor | 44 | 40 | 18 | 15 | 11 |
| Verified alternate, unselected | 6 | 4 | 4 | 3 | 3 |
| Other nomination on positive lane | 140 | 135 | 129 | 121 | 110 |
| Nomination on empty lane | 180 | 180 | 178 | 172 | 167 |

Twenty-two dense lanes have neither a recent same-radio donor nor a peer factor, including four with a published factor. Even removing the cost and coverage of all unconfirmed nominations leaves 18 published timing rows outside ±64 under this donor rule. Widening to ±1,024 examines about 489 timing bins per lane on average and still misses a quarter of the published timing rows. A causal scout must find those signals on the current antenna.

## Reproduce

The measurement uses the saved weak archive, existing private dense prefix and published detector bytes. Training sees deterministic test signals with both pilot edges and mixer signs. Three rotating repeats price complete native calls and the enclosed reduced timing work. The two new component tests exercise publication versus approximate identity, empty and positive classification, peer support and wrap tolerance. Six tests passed together with the first-phase oracle tests.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
tree=/home/mouse9911/gits/leo-tracker-reduxredux
private=/srv/bulk/leo-dev/leo-physical-stage-envelope-2j7mlwtt
dense="$private/fast8-auto-20261113-075937-d9ab96ee-1-lower-segment-00000000"
packet=(/var/tmp/leo-full-short-dense-DS30-0008/publication/fast-scan-automatic-work/*/detections.json)
work=$(mktemp -d /dev/shm/leo-v3-short-timing-lags.XXXXXX)
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env TMPDIR=/dev/shm OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$release/src:$release" timeout 70s "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.v3.short_timing_lags bench "$work/native" "$release/assets" \
  "$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip" "$dense" \
  "${packet[0]}" reports/ALGO08/v3/measurements/timing-only-oracle.json.gz > "$work/receipt.json"
```

The sealed raw receipt's uncompressed SHA-256 is `96ad73cac883ece79c3831933194bdcea3d6f50ef9abfad793a1e9f226410db1`. The early-route budget recomputes from its original per-lane clocks and changed-packet flags.
