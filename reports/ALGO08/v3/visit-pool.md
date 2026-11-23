# Causal raw-waveform CFO pooling across visits

Pooling raw pilot evidence across earlier visits beat the mismatched-channel control, but improved the latest-visit baseline by only **three factors per recording** at 4.55 kHz. It did worse at 400 Hz. Even with free timing, verification and perfect fallback routing, the measured sketch cost made every causal arm slower than full v3. [Frozen protocol](visit-pool-protocol.md) · [Per-lane proposals, hashes and timings](measurements/visit-pool.json.gz)

## What the waveform predicts

The sketch uses the released quarter-rate FIR on one original antenna, then applies the earlier four differential pilot lags on six frames. It ranks eight timing maxima and, for every signed CFO grid point, keeps the best lag-aligned score over those maxima. Robust per-visit contrast normalization and pooling of real marginal scores discard cross-visit phase. Each historical forecast uses only the last three or four scores from its own receiver, stream, edge, channel and actual RF. The flat pool uses a 1.2-second exponential time constant. The drift pool tests seven fixed slopes and retains the best aligned pooled score at each CFO. The null uses the neighboring mismatched channel from the same antenna with the same number of donor visits, decay law, drift grid and four proposal slots. [Waveform and causal proposal runner](visit_pool_trial.py)

The earlier bracket, anchor-sky and sparse-RF routes worked from verified factors or solved owners and orbit data. This probe has no labels, location, orbit or shared antenna phases as inputs. It fixes the proposals before calling the full two-scan detector on each target lane. The separate current-only control gets the same four slots from the target's own sketch. All arms are scored on the same mature lanes and do not transfer timing. [Brackets](../single-core-2x/receiver-brackets.md) · [Independent antenna evidence](../single-core-2x/receiver-lanes.md) · [Anchor sky](anchor-sky.md) · [Anchor census](anchor-orbit-census.md) · [Sparse RF recall](sparse-rf-recall.md) · [Differential waveform basis](differential-fold.md)

| Recording | Authenticated / admitted stereo visits | Mature / admitted antenna lanes | Eligible factors, primary / residual | Most recent same-RF visit, median elapsed |
|---|---:|---:|---:|---:|
| DS30-0008 | 128 / 128 | 208 / 256 | 113 / 59 | 0.354 s |
| DS30-0016 | 64 / 58 | 64 / 116 | 30 / 13 | 0.354 s |

There were four usable histories on 192 of 208 mature dense lanes and 40 of 64 transfer lanes. The others used three. The 48 and 52 remaining lanes had insufficient matched history for the primary comparison. The first recording supplies the dense development sample, and the second is a separate real recording from the same site. The scope covers three signed members and one retune pattern. It cannot estimate performance at an independent location.

## Signed CFO coverage and unsupported proposals

The comparisons count one-to-one matches. They use absolute signed frequency and allow no alias substitution. The four-slot budget gives 832 proposals on mature dense lanes and 256 on mature transfer lanes for every method. Each method filled four slots on all 95 and 34 stock-empty mature lanes respectively. An unsupported proposal is defined against the installed factor list and is not a decoded false alarm.

| Method | Dense matches ≤400 Hz | Dense matches ≤4,550 Hz, primary / residual | Dense entire positive lane sets covered | Transfer matches ≤400 Hz | Transfer matches ≤4,550 Hz, primary / residual | Transfer entire positive lane sets covered |
|---|---:|---:|---:|---:|---:|---:|
| Latest same-RF score | 12 | 47 / 16 | 31 / 113 | 1 | 7 / 2 | 3 / 30 |
| Unshifted pool | 9 | 51 / 15 | 29 / 113 | 0 | 10 / 2 | 4 / 30 |
| Drift-aligned pool | 8 | 45 / 11 | 23 / 113 | 0 | 4 / 1 | 1 / 30 |
| Mismatched-channel pool | 2 | 7 / 11 | 4 / 113 | 1 | 4 / 1 | 3 / 30 |
| Current visit only | 30 | 76 / 23 | 48 / 113 | 4 | 12 / 1 | 4 / 30 |

At the wide tolerance the unshifted pool left **766 of 832** dense slots and **244 of 256** transfer slots unsupported. It added four primary matches while losing one residual match relative to carry-forward on dense data, and it covered two fewer complete dense lane sets. A later verifier would still have to find valid timing and check the original waveform. No retrospective tuning was applied to recover weak residuals or distinguish persistent interference from pilots.

## Fallback and CPU envelope

The full native receiver averaged **2.802 ms per dense lane** and **2.610 ms per transfer lane**. The measured prototype sketch, including conversion, FIR and score generation, used **1.644 ms** and **1.634 ms** per lane before history alignment or ranking. These clocks cover resident waveforms. They exclude signed reading and publication.

| Best causal arm by modeled CPU | Original native CPU | Warm-up / missed-positive retries | Retry CPU | Fully covered positive lane CPU available | Total with sketch and ranking, and free timing/checks |
|---|---:|---:|---:|---:|---:|
| DS30-0008, latest score | 0.717 s | 48 / 82 | 0.475 s | 0.117 s | 0.911 s |
| DS30-0016, unshifted pool | 0.303 s | 52 / 26 | 0.244 s | 0.015 s | 0.437 s |

The oracle charges stock search on every warm-up lane and on each mature positive lane with any missed factor. It grants free recognition of empty lanes after warm-up and pays nothing for timing, verification, scheduling or the residual safety check. Even under those assumptions, break-even sketch cost would be **0.889 ms per dense lane** or **0.474 ms per transfer lane** at the measured ranking costs. The current-only comparator gives a lower floor than the past-only arms, and still costs 0.831 s and 0.434 s before timing or verification. A native rewrite could lower sketch cost. It would leave the missing signed coverage and the unproven fallback decision. This evidence stops the tested pooling route before timed verification or a full recording replay.

## Reproduce

Seven component tests passed, including drift direction, future history exclusion, matched history budgets, signed matching and full retry charging. Replay uses the pinned installed receiver, both physical bindings and the shared low-priority lock.

```sh
tree=/home/mouse9911/gits/leo-tracker-reduxredux
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
bindings=/srv/bulk/leo-dev/ds30-full-20261121/bindings
lock() {
  flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 timeout 55s "$@"
}
lock sudo -n -u leo env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.v3.visit_pool_trial /opt/leo-algo08/algo08v3/payload/receiver.so "$release/assets" \
  "$bindings/DS30-0008.json" "$bindings/DS30-0016.json" /srv/bulk > /var/tmp/leo-visit-pool.json
lock env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$tree/.venv/bin/python" -BPs -m pytest -q \
  tests/pipeline_eval/test_visit_pool_trial.py tests/pipeline_eval/test_receiver_differential_fold.py
```
