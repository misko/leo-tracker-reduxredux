# Stacking weak carrier scores across visits

Along a supplied exact signed trajectory, summing unthresholded pilot evidence recovered **three of four tracks** after weakening one saved simulation to an original-wave-to-added-noise ratio of −9 dB. Only **five of 76** individual visits reached the same four-slot carrier shortlist. At −12 dB the sum recovered one of four tracks. The native horizon-limited causal bank cost **1.62 ms per lane** in scoring alone, against approximately **0.60 ms per lane** for acquisition including verification. The available physical clips could not establish real weak-carrier gains. [Frozen protocol](track-before-detect-protocol.md) · [Complete receipt](measurements/track-before-detect.json.gz)

## Real repeat opportunities

The 18-visit DS26 weak-carrier archive contains at most two visits per exact RF in one recording. The 80 prospectively selected DS26/DS29 visits contain at most four, even when pooling distant opportunities. The distinct chronological staggered panel has three visits per RF in each 24-visit DS26-0197 or DS29-0316 block. The earlier 24-visit dense DS30-0008 slice likewise has at most three. These maxima grant the same satellite at every opportunity and still fall below the six-visit screen. The longer DS30-0016 archive had about 10–16% residency per compressed member when checked with `fincore`. Its raw I/Q stayed closed. [Chronological physical clip bindings](../../2026_11_19_receiver_screening/receiver-choice/staggered-native/source-lock.json) · [Earlier dense and weak slices](cyclic-carrier.md)

The southern development simulation's first 256-visit block tied for the strongest same-satellite support. Four receiver/RF tracks cover two satellites, with 19 observations each at two-second cadence over 36 seconds. Each active track has a selected factor on every expected visit. The complete block has 428 of 512 antenna lanes without any selected factor. The owner witness, archived signed measurements and installed v3 packet match by sealed input and stable observation ID. The installed receiver agrees on the signed measurements. Only the four authenticated compressed members of this single simulation block were decoded. [Owner witness](measurements/directed-donor-owner-witness.json.gz)

## What the oracle recovered

The scout exports the earlier lag-one nonconjugate comb's entire signed score surface with 16,384 disjoint products per lane. It standardizes each surface, interpolates at the proposed signed frequency, and sums along a track. Measured CFO, ownership, exact RF and the positive support are supplied to the oracle. It receives no pilot epoch or intervisit phase. Each alternative shifts the entire trajectory in 1 kHz steps across its common signed tuner interval, preserving its cadence, duration and RF. The false comparisons use offsets beyond 4.55 kHz. Each track had 1,493–1,557 such alternatives. The shortlist keeps up to four offsets separated by 10 kHz and checks whether any falls within 4.55 kHz. Individual visits use the same contour offsets.

| Condition | Individual owned visits in top four | 19-visit tracks in top four | Exact offset ranks on the four tracks |
|---|---:|---:|---|
| Saved southern I/Q | 76/76 | 4/4 | 1, 1, 1, 1 |
| Saved wave with −9 dB wave-to-added-noise power | 5/76 | 3/4 | 3, 1, 21, 1 |
| Saved wave with −12 dB wave-to-added-noise power | 2/76 | 1/4 | 682, 4, 262, 25 |
| Independent proper white noise | — | 0/4 | — |
| Zero samples | — | 0/4 | All offsets tied |

The original wave's total input power sets each attenuation level. It includes the simulation's native noise, and the ratio has no calibrated physical pilot-to-noise equivalent. Requantizing the added noise saturated no components at either level. The two antennas sample the same two satellite families, which limits the independent evidence. The four original blank controls each use eight same-receiver, same-RF empty visits over 14 seconds, with identical gaps to an active contour subset. None entered the top four. The full 36-second positive tracks had no empty visits. These controls compare trajectory discrimination and still allow the ungated method to emit false proposals. Both power levels reuse the same simulation. Residual companions, waveform timing, original-sample verification and position remain unmeasured. [Signed and control scores](measurements/track-before-detect.json.gz)

## Charge the causal search and hold the I/Q

The native surface averaged **0.066 CPU ms per lane**, including exporting and normalizing Float32 scores. The causal catalogue and projection charged about 1.40 and 0.14 CPU seconds, respectively. The projection uses the supplied offer and past archive. Its clock also includes a four-corner diagnostic. Every orbit kept by the causal visibility screen has 228 offset cells per 227.273 kHz alias period and all allowed signed lifts. The native bank accumulates linearly interpolated scores and checks band bounds. The cost screen grants one region center and ends at score accumulation, before ranking families or searching receiver nuisance drift, visibility gaps, or start times.

| Native bank scope | Mean satellite count per lane | In-band signed cell reads, 512 lanes | Search CPU s | Search CPU ms/lane | Dense 13,530-lane search CPU projection |
|---|---:|---:|---:|---:|---:|
| Original broad causal visibility screen | 1,340 | 1,101,045,476 | 2.260 | 4.413 | 59.71 s |
| Instantaneous geometric horizon at the supplied center | 524 | 430,600,800 | 0.827 | 1.615 | 21.85 s |

The horizon bank alone would use 2.78 times the measured dense CPU callback allowance of 7.86 s, even before charging about 0.89 s for all surfaces, catalogue preparation, epoch search, original-sample confirmation and signed cancellation. The dense projection holds the southern catalogue mix and per-lane throughput fixed and is not a second measured recording. The 25 km region's corner witness moved signed model CFO by up to 14.3 kHz, apart from unknown orbit and receiver errors. Searching more region points and retaining each alias could add work. This result prices the implemented native accumulation, with scope for a different orbit nomination or score reuse algorithm. [Complete dense budget](acquisition-split.md) · [Earlier solved-sparse carrier recall](sparse-rf-recall.md) · [Exact verification cost](directed-verifier.md)

The simulated block carried about 21.47 MB of unthresholded surfaces and 409.6 MB of decoded stereo I/Q. The same surface format across 13,530 dense lanes would take about 568 MB. A streaming bank can discard used surfaces. Verification at original sample resolution still needs the underlying samples after the stack is decided. Waiting a 36-second dense window at the recorded average stereo rate implies about 1.30 GB of decoded I/Q, or an authenticated reread. Even with a perfect trajectory, the previous original-sample directed verifier required precise epoch information. The earlier quantized-CFO experiment also lost position accuracy even when it kept the complete factor set. The current result stops at a coarse signed-frequency oracle and its search cost. [Sparse anchor storage accounting](anchor-orbit-census.md) · [Carrier precision and position](carrier-grid.md)

## Reproduce

Run on one Gauss core using the shared exclusive benchmark lock, CPU 2, nice 15, ionice best effort 7 and one numerical thread. The runner checks both signed native documents and their terminals, the owner receipt, TLE snapshot hashes, the original installed pilot bytes and the simulation's sealed inventory. It reads no DS30 raw samples. Thirteen focused tests passed for cyclic carriers, the new surface and bank, and the existing causal geometry helper. [Runner](track_before_detect.py) · [Native kernel](../../../tools/pipeline_eval/variants/experimental/receiver_cyclic_carrier.c) · [Tests](../../../tests/pipeline_eval/test_algo08v3_track_before_detect.py)

```sh
bench=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
release=/opt/leo-algo08/current
code="$PWD/reports/ALGO08/v3"
scratch=$(mktemp -d /dev/shm/leo-track-before-detect.XXXXXXXX)
lock() {
  flock -x "$bench/gauss.lock" nice -n15 ionice -c2 -n7 taskset -c 2 timeout 70s \
    env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONPATH="$code:$PWD:$PWD/src" \
    "$release/venv/bin/python" -BPs "$code/track_before_detect.py" "$@"
}
lock build "$scratch/surface.so"
lock trial "$scratch/surface.so" "$release/assets" \
  /tmp/leo-regional-qZJKBw4W/public/6bd1f26bfa0bedfcf3f100f8 \
  "$bench/integration-shared/pairs/south/pair.json" \
  "$bench"/integration-shared/pairs/south/candidate/fast-scan-automatic-work/*/detections.json \
  "$bench"/exact-curved-lookahead-south-inside/candidate/fast-scan-automatic-work/*/detections.json \
  "$code/measurements/directed-donor-owner-witness.json.gz" \
  "$tree/reports/2026_11_19_receiver_screening/receiver-choice/staggered-native/source-lock.json" \
  /srv/bulk/leo-dev/algo08v2-ds30-100-6cdbac/v3-bounds-DS30-0008-pair/baseline/fast-scan-automatic-work/*/detections.json \
  "$scratch/receipt.json" \
  --zip "$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip" \
  --zip /srv/bulk/leo-dev/ds26-two-carrier-20261120/prospective-iq.zip
```
