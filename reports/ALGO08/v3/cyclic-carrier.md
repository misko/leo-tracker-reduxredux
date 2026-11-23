# Carrier-first cyclic spectrum loses recorded pilot evidence

The lag-one nonconjugate scout found **0 of 58** weak factors and **1 of 54** dense factors within 4.55 kHz using four signed proposals. Doubling its aperture raised coverage to **1 of 58** and **2 of 54**. Both versions found all 16 noiseless planted carriers across the two pilot edges and both signs. The saved-waveform result stops this design before timing extraction and independent verification. [Prespecified screen](cyclic-carrier-protocol.md) · [Native clocks and waveform receipt](measurements/cyclic-carrier.json.gz)

## What the installed pilots preserve

For a single pilot with starting sample (d), let (x[n]=A,s[n-d]exp(2pi i f n/F_s)). The product (x[2m]x[2m+1]) multiplies a periodic pilot product by an oscillator at (2f). Shifting the pilot changes harmonic phases while leaving its ideal line magnitudes unchanged. Using disjoint pairs gives 5 MS/s and keeps the entire 3.2 MHz doubled carrier interval distinct modulo the sample rate. Unknown harmonic identity creates short aliases even in that interval. The finite Hann aperture limits line resolution and introduces leakage absent from the exact-period asset calculation.

| Feature of the exact pilot synthesis table | Lower edge | Upper edge |
|---|---:|---:|
| Strongest square-power line, fraction of transformed energy | 0.335% | 0.281% |
| Strongest fourth-power line | 0.233% | 0.173% |
| Strongest lag-one nonconjugate line | 0.332% | 0.260% |
| Lag-one top-16 coefficient energy at unit pilot RMS | 0.0559 | 0.0511 |

The square-power coefficient at zero harmonic is only 0.0012 and 0.0121 at unit pilot RMS. Lag one has the most top-16 energy after division by the ideal proper white noise product variance among the tested short lags on both edges. The scout looks up these 16 harmonics and weights on each edge, computes one complex FFT per scan, and ranks offsets by interpolated and weighted line powers. It scores approximately 10,486 or 20,972 shifts, with four signed proposals separated by at least 10 kHz. The two apertures span 3.28 and 6.55 ms. The earlier differential fold used conjugate products and searched epochs before signed CFO. The earlier shared-ambiguity screen approximated a linear two-dimensional pilot bank. [Native scout](../../../tools/pipeline_eval/variants/experimental/receiver_cyclic_carrier.c) · [Differential fold](differential-fold.md) · [Linear span](shared-ambiguity.md)

At the true carrier and pilot timing, the ideal independent-noise model assigns total line energy over noise variance ( (2N/3)ho^2 sum_{k=1}^{16}|C_k|^2 ), where (ho) is the pilot-to-noise power ratio and (2N/3) is the Hann effective sample count. At −15 dB that ratio is 0.61 and 0.56 for the lower and upper edges at 16,384 products. Even using all 20 ms at this ratio gives 3.72 and 3.41. This calculation grants known spectral alignment and excludes the signal–noise products, colored interference, unknown-delay ranking and whole-band search. With two carriers, an additional mixed product lies around the sum of their CFOs, so it enters the doubled-frequency spectrum near the midpoint carrier, with amplitude proportional to the product of both amplitudes. The weak carrier's own line scales with its amplitude squared. Real signed cancellation removes much of a confirmed primary but leaves quantization, residual model error and other signals. The saved experiment measured that residual directly.

## Saved coverage and cost

The 18 weak stereo visits cover both pilot edges. The 24 dense DS30-0008 stereo visits use the lower asset. Reference factors came from the installed matched-PGO v3 binary. The exact installed first-scout and signed CI16 cancellation entries expose every reached residual scan to the carrier-first test. The recorded zero mixer centers set the signed search interval. Each candidate sees only its original lane, the asset table and this interval. The same ranking runs over lanes and scans with or without a verified factor.

| Slice and rank | Installed factors | Top-four matches at 16,384 products | Top-four matches at 32,768 products |
|---|---:|---:|---:|
| Weak lower primary | 20 | 0 | 0 |
| Weak lower residual | 12 | 0 | 1 |
| Weak upper primary | 16 | 0 | 0 |
| Weak upper residual | 10 | 0 | 0 |
| Dense lower primary | 33 | 1 | 1 |
| Dense lower residual | 21 | 0 | 1 |

Every match was third or fourth in its shortlist. The short scout emitted 288 weak and 324 dense proposal slots, with 288 and 323 unsupported by an installed factor. The longer scout left 287 and 322 unsupported. The controlled −6 dB plants were better, with 6/8 lower and 5/8 upper at the short aperture, and 7/8 lower and 8/8 upper at the long aperture. Separate white-noise and CW controls also emitted four proposals per scan. At both lengths the output is an ungated list of hypotheses. These measurements make no final false-alarm, continuation or position claim. [Per-lane lists and controls](measurements/cyclic-carrier.json.gz)

| Trial | Native scout CPU per scout, ms | Dense CPU per lane, both reached scans, ms | Dense CPU with perfect fallback routing, ms per lane | Weak CPU with perfect fallback routing, ms per lane |
|---|---:|---:|---:|---:|
| 16,384 products | 0.078–0.079 | 0.132 | 2.768 | 4.214 |
| 32,768 products | 0.164–0.165 | 0.277 | 2.992 | 4.385 |

The initialized native clocks include CI16 loading, product and taper, FFT, power, comb scoring and ranking. CPU per lane adds every reached residual scout. The matched stock native receiver used 3.133 ms per dense lane and 4.057 ms per weak lane. Perfect fallback routing grants free knowledge of all omitted factors and skips full native work on empty lanes. It still requires 32 or 33 of 48 dense full retries and all 36 weak retries, before any timing or verification of the new proposals. The 0.60 ms lane target already includes verification. On the earlier distinct dense prefix the existing guarded verifier consumed 0.536 ms per lane with two perfect proposals and a known factor-presence oracle. Both aperture costs would exceed 0.60 ms when added to that favorable verification model. Authenticated acquisition outside detector callbacks adds further cost at the recording level. [Directed verifier](directed-verifier.md) · [Complete acquisition split](acquisition-split.md)

## Reproduce

Use the current installed release assets, the installed v3 detector, the pinned weak archive and the dense DS30-0008 binding. Under the shared Gauss lock, build `cyclic_carrier_trial.py build NEW_LIBRARY` on CPU 2 with nice 15, ionice best effort 7 and one numerical thread. Then run `cyclic_carrier_trial.py trial NEW_LIBRARY INSTALLED_RECEIVER ASSETS WEAK_ARCHIVE DS30_BINDING BULK_ROOT NEW_RECEIPT` as the read-only capture account in the installed Python environment. Set `PYTHONPATH` to the worktree's `reports/ALGO08/v3`, root and `src`. The trial authenticates the archived I/Q and explicitly caps the prefix. Four component tests passed for modulation phase, quadratic noise scaling, both signed wraps and complete retry charging. [Runner](cyclic_carrier_trial.py) · [Tests](../../../tests/pipeline_eval/test_algo08v3_cyclic_carrier.py)
