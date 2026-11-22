# Saved public north and south face comparison

The previous public boundary pairs crossed the east and west faces with the offer centered at the true receiver latitude. This comparison crosses a latitude face on each of the same two public waveforms and offsets both coordinates of every new offer. It compares deployed ALGO08v2 with frozen covariance build `375895c3`. Each solver receives its own saved detector output from the published waveform pair and the original capture-time TLE archive. Earlier comparison of the two detector files found the same winning ranks, times and CFOs at both sites. [Original public waveform pairs](covariance-publication.md)

The offers were frozen in commit `3b08c747d` before the solves. A balanced rule assigned the northern waveform a north face with its center 3.125 km east of truth, and the southern waveform a south face with its center 3.125 km west of truth. The tangent offset is one eighth of the 25 km width, measured at the reference latitude. Longitude stays fixed within each pair. The centers put the true point exactly 100 m inside or outside the chosen face in the release's north coordinate, which uses 111 km per degree. In each offer the solver uses the region center as its screen center. Both center coordinates differ from the corresponding reference coordinates. [Prespecified geometry, offer hashes and published-input pins](measurements/covariance-latitude-offers/manifest.json)

Each of the four solver and waveform combinations first replayed its published anchor and checked the positions, RF RMS and satellite owner digests for both calibration arms. Then it ran the inside and omitted offers. The order reversed between the two waveforms. The solver workers received the saved detections, the archive and one offer per invocation. Scoring used the existing public synthetic references after all solver outputs closed. [Saved-input replay adapter](replay_region_offers.py) · [Public scoring references](../regional-release/scoring-key.json)

## Results

Each build and calibration arm returned **2 of 2 valid fixes** for containing offers and **2 of 2 false fixes** for omitted offers. The four anchor replays matched their original publications. The two builds also returned identical positions, RF RMS and satellite owner maps on all four new offers. The owner maps were constant across the three offers on each waveform, with 302 owners north and 266 south in each calibration arm. [Scored results and per-offer receipts](measurements/covariance-latitude-faces.json)

| New offer | Decision in both builds and arms | Horizontal error, fixed zero | Horizontal error, fitted c | RF RMS, fixed zero | RF RMS, fitted c |
|---|---|---:|---:|---:|---:|
| North · 100 m inside | Valid fix | 745.2 m | 712.5 m | 5.3797 Hz | 5.1727 Hz |
| North · 100 m omitted | False fix | 758.9 m | 712.7 m | 5.3770 Hz | 5.1727 Hz |
| South · 100 m inside | Valid fix | 470.4 m | 461.6 m | 6.4405 Hz | 6.3269 Hz |
| South · 100 m omitted | False fix | 504.6 m | 494.3 m | 6.4235 Hz | 6.3163 Hz |

Fitting `c` reduced frequency RMS and horizontal error in all four offers. The omitted offers remained false fixes. Both southern estimates sat on the offered south face for both offers. On the northern omission, the fixed-zero estimate was on the north face and the fitted estimate was about 103 m inside it. The near-omission failure therefore occurs with offsets in both center coordinates and with latitude faces on these two public development waveforms.

## Reproduction

Use the offers and original publication receipts pinned in the manifest. The commands below replay the saved files in the registered order using one low-priority worker on CPU 2. The output directory must be new.

```bash
p=/tmp/leo-algo08v2-2x-bench
r=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
offers="$PWD/reports/ALGO08/single-core-2x/measurements/covariance-latitude-offers"
export PYTHONPATH="$PWD:$PWD/src:$r"
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
flock "$p/gauss.lock" nice -n 15 ionice -c 2 -n 7 taskset -c 2 bash -s -- "$p" "$r" "$offers" <<'SH'
set -e
p=$1 r=$2 offers=$3
spec=sha256:375895c3afda3abd3a916f90bbd63248b5e792f70c78a0e4f136c9bf1a79d423
result="$p/covariance-latitude-face-repeat"
mkdir "$result"
for replay in north:baseline north:candidate south:candidate south:baseline; do
  site=${replay%:*}
  method=${replay#*:}
  "$r/venv/bin/python" -B -m reports.ALGO08.single-core-2x.replay_region_offers \
    "$p/covariance-$site-inside/pair.json" "$p/integration-covariance-posterior" "$spec" \
    "$result/$site-$method.json" "$offers/$site-inside.json" "$offers/$site-omitted.json" \
    --method "$method"
done
SH
```
