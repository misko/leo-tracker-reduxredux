# Reciprocal RF-channel checks miss both 100 m omissions

The frozen channel-fold rule retained all three containing offers and flagged the **1.5 km India omission** for possible withholding. It missed **both the northern and southern 100 m omissions**. The original all-channel bilateral sign check already retained all three valid offers and flagged both India and the southern omission. The fold exercise preserved the India result and reduced omission recall on these public inputs. Every official solver and publication decision stayed in place. [Frozen protocol](geographic-rf-fold-protocol.md) · [Numeric summary](measurements/geographic-rf-fold-summary.json) · [All probe scores and track terms](measurements/geographic-rf-fold.json.gz)

## Fixed split and matched evidence

The rule places original channels by ascending ordinal into two folds. Both antennas, every observation on a channel and every complete Graph track on it stay together. A training fold uses the pooled released orbit-mixture score to choose one inside and one exterior point on the original 96-point lattice. Each receiver in the opposite fold then evaluates those same coordinates. All four held gains must be strictly positive to flag a possible withholding. Tied training maxima or an empty fold at either receiver would abstain. All six offers had complete folds and unique training maxima. Earlier experiments partitioned time or orbits, or changed antenna/channel acquisition schedules. This experiment keeps the original packet and splits only geographical score contributions. [Implementation](geographic_rf_fold.py) · [Earlier regional scoring and held-block comparisons](../single-core-2x/regional-reassignment.md)

The archived evidence contains aggregate scores and top-supported owners at each location. A single instrumented pass recovered the individual track likelihoods and reproduced all **576 original points** exactly, including coordinates, pooled scores, receiver scores and owners. India used its two existing waveform offers. North and south each used their original 100 m inside and 100 m outside mirrored offers on the same respective detector bytes. Scores retain all original observations in the denominator. Observations outside Graph tracks contribute zero. [Original India scores](india-regional-diagnostic.md) · [Published north/south mirrors](../single-core-2x/mirrored-regions.md) · [Exact score archive](measurements/geographic-rf-fold.json.gz)

## Held gain and transfer

The table gives exterior minus inside score per original held observation, multiplied by 1,000. Each pair contains receiver 1 and receiver 2 in that order. The bilateral all-channel comparison uses each receiver's original best points.

| Public offer | Held gains with fold 0 training | Held gains with fold 1 training | Original pooled sign | Original bilateral sign | Frozen fold decision |
|---|---:|---:|---|---|---|
| India containing | −19.082 / −17.449 | −17.010 / −16.828 | Keep | Keep | Keep |
| India, 1.5 km outside | +13.187 / +11.868 | +8.461 / +9.531 | Flag | Flag | Flag |
| North, 100 m inside | +88.826 / +106.371 | −0.995 / −1.034 | Keep | Keep | Keep |
| North, 100 m outside | +94.685 / +112.256 | −0.960 / −0.998 | Keep | Keep | Keep, omission missed |
| South, 100 m inside | +0.00479 / −0.03209 | −0.11773 / +0.29758 | Flag | Keep | Keep |
| South, 100 m outside | +0.02462 / −0.01359 | +0.10855 / +0.52377 | Flag | Flag | Keep, omission missed |

Both India folds independently chose the same original inside and outside coordinates. On the omitted offer both chose the point 3.125 km past the north face. Both northern offers generated the same conflicting signs when the folds swapped. Fold 0 chose an inside point 6.25 km west of center, while fold 1 chose the inside point 12.402 km west. Both chose the same exterior point 12.598 km west. Both southern folds chose the nearest pair across the east face on both offers. Receiver 2 on held fold 1 favored the inside point on the omitted offer, which blocked the flag. [Selected coordinates and training margins](measurements/geographic-rf-fold-summary.json)

The folded picks had disjoint sets of best-supported NORADs across RF folds at every nominated point. The underlying mixture still permits the same full causal satellite hypotheses in each fold. Both antennas on one channel share its fold, and all folds share a recording, receiver equipment and timing, the same sky and model, and the same offered lattice. Fold coverage was also unequal. For both north and south, each antenna supplied 133 observations to one fold and 95 to the other. India contributed 223/138 on receiver 1 and 216/147 on receiver 2. These results establish directional consistency where the evidence transfers. The six offers come from three development waveforms and supply no calibrated false-withhold probability or independent confidence level. [Fold coverage and satellite overlap](measurements/geographic-rf-fold-summary.json)

## Cost and reproduction

The shared Graph and causal catalogue took **0.124–0.166** and **1.402–1.484 CPU seconds** per waveform respectively. The original all-probe pass with individual term capture took **0.788–1.365 CPU seconds per offer**. The fold computations and nomination readout added **0.38–0.52 ms per offer** after the track terms were available. The diagnostic opened no raw recording, ran no position fit and made no changes to the existing terminal or raw-bound plan. [Charged clocks](measurements/geographic-rf-fold-summary.json)

Use a fresh output directory. Run `geographic_rf_fold.py run SITE DIR/SITE.json` for `india`, `north` and `south`. After the three files seal, use `score DIR SUMMARY FULL` with the checkout `reports/ALGO08/v3`, repository root and `src` on `PYTHONPATH` under the same lock. Twenty-six focused tests passed. [Runner](geographic_rf_fold.py) · [Component tests](../../../tests/pipeline_eval/test_geographic_rf_fold.py)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
lock=/tmp/leo-algo08v2-2x-bench/gauss.lock
flock -x "$lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 90s \
  env PYTHONPATH="$PWD/reports/ALGO08/v3:$payload:$release/src:$release:$PWD" \
  OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/v3/geographic_rf_fold.py \
  run "$site" "$out/$site.json"
```
