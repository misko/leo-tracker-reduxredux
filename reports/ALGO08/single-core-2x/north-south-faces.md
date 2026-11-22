# Public boundary tests with offsets in both coordinates

Both deployment and the frozen spectral build published the two valid fixes and **both false fixes**. Every compared coordinate, frequency residual and observation-owner digest matched between builds at each offer. Changing the orientation and center of the valid offer with the signal held fixed increased northern fixed-zero error from 106 m to 745 m. Southern fixed-zero error decreased from 817 m to 470 m. The satellite assignments stayed the same within each site across all three fits. The position change therefore survived even with stable assignments. [Complete bound measurements](measurements/north-south-faces.json)

| Public site | Receiver relative to new face | Fixed-zero / fitted position error, m | Fixed-zero / fitted RF RMS, Hz | Decision, both builds |
|---|---|---:|---:|---|
| Northern | 100 m inside | 745 / 712 | 5.380 / 5.173 | Valid fix |
| Northern | 100 m outside | 758 / 712 | 5.377 / 5.173 | False fix |
| Southern | 100 m inside | 470 / 461 | 6.440 / 6.327 | Valid fix |
| Southern | 100 m outside | 504 / 494 | 6.424 / 6.316 | False fix |

Neither new offer discloses the receiver's latitude or longitude. These additional failures show that the previous false fixes can also occur on north–south faces. The four offers use two previously examined signals and add no new physical site.

## Prespecified test

The previously published east–west search squares used the simulated receiver's latitude as the square's latitude. Test the same frozen spectral receiver and solver against deployment with north–south faces and a nonzero east offset. This changes both coordinates of the geographic prior. Use saved detections from the two existing public raw pairs, keeping each build's detector output and the original capture-time orbit archive fixed. The new offers go through the entire position solve, including satellite nomination, inference and the publish/withhold decision.

Before examining the decisions, fix the width to 25 km, the east offset of the receiver relative to the center to +5 km in the northern case and −5 km in the southern case, and the north offset magnitude to 12.4 and 12.6 km. Use the north face for the northern case and the south face for the southern case. Recompute the center longitude at the center latitude so that east displacement is exactly matched in the local frame. The receiver is 100 m inside or outside. Each solver receives the square and uses the same center for satellite screening. The driver checks signs and offsets with the evaluator and reproduces the original containing offer before scoring the changed offers.

Count correct fixes and false fixes separately for each build. Report both calibration arms' position errors and RF residuals, including a null result if a fit is withheld. The public locations were already used in development. These are two additional boundary orientations on existing recordings. No reserved location or new raw recording enters this test.

## Reproduction

Run the existing saved pairs from the [spectral publication](spectral-publication.md). Supply the Gauss benchmark directory and a new output directory to the [replay driver](north_south_faces.py) under the shared single-core lock. The driver checks the original pair receipts byte for byte and repeats each build's original offer as an anchor.

```sh
bench=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 env \
  PYTHONPATH="$PWD:$PWD/src:$release:$release/src" OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 "$release/venv/bin/python" -BPs -m reports.ALGO08.single-core-2x.north_south_faces \
  "$bench" "$bench/public-north-south-face-pairs"
```
