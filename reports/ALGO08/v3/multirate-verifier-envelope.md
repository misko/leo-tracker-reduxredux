# Multirate verification would have too little of the measured receiver budget

Giving **all 20 and 12 ms native receiver work away** in the complete dense acquisition yields a modeled **0.661 median / 0.631 summed** elapsed ratio across the first four enrolled recordings. Both ratios must be at most 0.500. Even a free native detector leaves far more work than a multirate verifier can remove on that measured path. On the fastest three-member prefix, a **2× speedup of the entire short receiver** would still miss the median, and a **4× speedup would have to apply to 96.7%** of the short receiver's measured time. [Frozen screen](multirate-verifier-envelope-protocol.md) · [Pilot measurements and per-recording model](measurements/multirate-verifier-envelope.json)

## Power after carrier-centered decimation

The existing timing scout uses 2.5 MS/s with signed search across ±800 kHz. Its previous 1.25 MS/s reduction folds parts of that carrier range and retained roughly 54–66% of the quarter-rate pilot power after filtering. The new representation is a *post-nomination* verifier. It grants a correctly mixed carrier center and considers ideal low-pass filtering before decimation. This removes the need to fit the whole unknown signed search band into one reduced-rate stream. The check uses both original pilot edge assets and the exact and rolled templates for the actual GLRT aperture, starting at symbol two and covering 64 symbols of 44 native samples. The ideal spectral projection is evaluated at residual −1, 0 and +1 kHz. [Prior rate and aliasing screen](../single-core-2x/receiver-rate.md) · [Original independent verification](directed-verifier.md)

| Complex output rate | Ideal coherent aperture power retained | Ideal summed symbol-template power retained | Lowest individual symbol across both edges and controls |
|---|---:|---:|---:|
| 1.25 MS/s | 64.67–67.30% | 64.86–66.03% | 51.10% |
| 2.50 MS/s | 97.78–97.94% | 97.47–97.78% | 88.48% |
| 5.00 MS/s | 99.23–99.29% | 99.02–99.19% | 93.59% |

The coherent result uses the complete 2,816-sample section. The summed result projects each 44-sample template separately, because the verifier forms individual symbol correlations before its spectral score. For a template `t` and received vector `x`, an ideal band projection `P` omits the correlation of their out-of-band components. Its normalized magnitude can be as large as the square root of the product of their omitted energy fractions. At 2.5 MS/s the weakest symbol leaves **11.52%** of its template energy outside the ideal band, permitting a term as large as **0.339** without a received-power bound. This is a correlation term, separate from the original nonlinear maximum and exact-minus-rolled gate. A certificate would need bounds on both templates and the actual received energy. A practical filter, fractional interpolation, CFO refinement, wrong proposals and exact fallback would add work. The pilot-only test supplies no signed-factor accuracy or false-alarm measurement.

## How much waveform time the enrolled gate needs

The model uses the frozen DS30-0374, DS30-0008, DS30-0155 and DS30-0001 roster, published historical v3 elapsed denominators, the **26.105 s** measured dense saved solver relative to its **60.966 s** historical numerical reference, and the existing once-per-recording and tail charges. It reproduces the required effective acquisition rate of **309.505 MB/s** for the median and **274.282 MB/s** for the summed gate. Each scenario subtracts a designated span from one actual verified acquisition clock, then applies that effective rate to each recording's signed compressed byte count. The removal assumes unchanged outputs, solver, tails and remaining acquisition time. It does not assign per-case physical cache behavior. [Measured regional solver and frozen projections](regional-dense-pair.md) · [Panel inventory and historical clocks](measurements/acquisition-throughput.json)

| Hypothetical acquisition change | Complete physical dense rate, MB/s | Complete-source median / summed | Fastest dense prefix rate, MB/s | Prefix-source median / summed |
|---|---:|---:|---:|---:|
| Measured source span | 135.354 | 0.833 / 0.808 | 231.518 | 0.587 / 0.555 |
| 2× all short native calls | 151.369 | 0.770 / 0.743 | 280.215 | 0.527 / 0.494 |
| 4× all short native calls | 160.888 | 0.739 / 0.711 | 313.149 | 0.497 / 0.463 |
| All short native calls free | 171.684 | 0.708 / 0.679 | 354.856 | 0.467 / 0.432 |
| All native waveform calls free | 190.916 | 0.661 / 0.631 | 440.542 | 0.415 / 0.387 |
| All acquisition CPU free, other elapsed fixed | 291.739 | 0.516 / 0.482 | 4,869.589 | 0.222 / 0.217 |

The complete dense recording has **8.182 GB** compressed. Its measured acquisition was **60.449 s elapsed / 32.403 s CPU**, including **17.592 s elapsed / 17.351 s CPU** in all native calls. The modeled median gate would allot only **26.436 s** for that input. The required **34.013 s** reduction exceeds every native call combined and exceeds total measured acquisition CPU under fixed off-core time. Using the complete recording's modeled zero-native rate, the four projected elapsed clocks in enrollment order are **59.990, 72.660, 58.148 and 63.650 s**, or **0.707, 0.643, 0.521 and 0.679** of their historical clocks. Fixed off-core time is a sensitivity assumption. Storage service and scheduling can vary. [Complete physical timing](dense-full-short-raw.md)

The faster three-member source is **232.084 MB** with **1.0024 s** observed elapsed and **0.3484 s** in short native calls. It would need to save **0.2526 s**, or **72.5%** of the entire short path, before paying for any new filter or fallback. Even a perfect 4× stage speedup would need to cover 96.7% of that path. The closest existing measured control with free exact proposals clocked the original 20 ms full detector's dense verification at **0.605 ms per issued lane**, around **22%** of its complete installed native path. That source includes both scans and supplies no measured 12 ms verifier fraction. Even assuming a substantially larger short verifier share leaves the optimistic prefix gate beyond a verifier-sized change. [Signed cold prefix](full-short-cold.md) · [Measured original verifier boundaries](measurements/directed-verifier.json.gz)

The power calculation and workload ceiling stop this candidate before a receiver prototype. They use only the existing receipts and shipped pilot assets. Two component tests passed. [Calculation and pin checks](multirate_verifier_envelope.py) · [Tests](../../../tests/pipeline_eval/test_multirate_verifier_envelope.py)

## Reproduce

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$release/src:$release" PYTHONDONTWRITEBYTECODE=1 \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.multirate_verifier_envelope \
  "$release/assets" "$fresh_output"
```
