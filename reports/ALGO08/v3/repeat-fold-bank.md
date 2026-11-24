# Coherent repeat FFT leaves a costly signed-carrier search

The best exact quarter-rate bank took **1.499 ms of thread CPU per 12 ms lane**, with half the circular delays, the true repeat-axis frequency granted, and folding, preprocessing, ranking and verification free. Its inverse transforms alone took **0.923 ms**. The dense 3.490 s saving target permits **0.113 ms per lane** for a timing-and-carrier replacement, or **0.356 ms** with all existing front-end work removed. The candidate fails even the larger allowance. [Frozen protocol](repeat-fold-bank-protocol.md) · [Timing receipt](measurements/repeat-fold-bank.json.gz)

## What folding shares

At native 10 MS/s the exact sampled period (P) is 40,000 samples, spanning three nominal 750 Hz pilot frames. Quarter rate gives (P=10{,}000) with the same 250 Hz lift spacing. An FFT across the three complete 40,000-sample repeats in 12 ms has 83⅓ Hz bins within that 250 Hz band. A single-frame residue with 750 Hz spacing requires resampling or rational polyphase interpolation. It also remains ambiguous in sign. For either period write the signed frequency as (f=(k+\rho)F_s/P), where (k) is an integer and (\rho) lies in one unit interval. For known weights (w_{r,j}) and delay (d) the complex matched sum is

\[
\begin{aligned}
y_\rho[j] &= e^{-2\pi i\rho j/P}\sum_r w_{r,j}x[rP+j]e^{-2\pi i\rho r},\\
C_f[d] &= \sum_j y_\rho[j]e^{-2\pi ik j/P}\overline{p[(j-d)\bmod P]}
 = \operatorname{IFFT}_h\!\left(Y_\rho[(h+k)\bmod P]\overline{\hat p[h]}\right)[d].
\end{aligned}
\]

The lift (k\) disappears across repeats. It survives within each repeat and cyclically shifts the shared forward spectrum. Each lift then acts on a different set of products with the fixed pilot spectrum. The measured frequency-major bank recovers all delays per lift with one inverse transform. For stride-two delays, summing pairs of spectral aliases before a half-length inverse gives exactly the even delays. Restoring candidate-local carrier phase, if needed by a downstream statistic, is an additional unit rotation at the actual absolute delay. [Native multiplication and decimation](repeat_fold_bank.c)

The full ±800 kHz legal interval holds at least 6,400 lifts at 250 Hz, or 2,133 at 750 Hz. Even granting the true residue and any carrier inside ±4.55 kHz of a scored lift, one row spans at most 37 or 13 feasible lifts, respectively. This gives favorable floors of **173 and 165 rows** for this bank. That tolerance is the earlier wide proposal match rule. It grants usable nominations at large mismatch and is much coarser than the released scout's 610.35 Hz grid. At half that released bin spacing around the carrier, the same count gives at least 2,134 or 2,133 rows. [Released carrier geometry](carrier-fft-bound.md) · [Wide nomination rule](joint-pilot-holdout.md)

## Generous bank cost

The existing guarded short receiver averaged **0.994 ms** per complete short native call on an authenticated DS30-0169 member. Its independently traced timing and carrier costs, normalized to actual dense short-call CPU, total **4.831 s across 11,834 short calls**. Giving away unpack, FIR and both frame modes increases the grant to **7.703 s**. These archived projections bound the opportunity targeted here. The new clocks below are isolated FFTW3f kernel measurements on CPU2 with synthetic data, nine paired repetitions and one- and eight-row plans. Each row reports the faster median per arm. The operation model counts six real operations per complex product, two per thinned spectral alias addition, and (5N\log_2N) per (N)-point complex inverse. This operation model prices the implemented factorization. [Complete current short-stage profile](short-primary-fusion-profile.md) · [Conditional 3.490 s target](warm-recording-budget.md)

| Folded layout | Delay stride | Inverse rows × length | Modeled Mflop per lane | Inverse-only CPU (ms) | Multiply and inverse CPU (ms) |
|---|---:|---:|---:|---:|---:|
| Exact native-grid period | 1 | 173 × 40,000 | 570.47 | 9.693 | 12.020 |
| Exact quarter-rate period | 1 | 173 × 10,000 | 125.32 | 1.781 | 2.343 |
| Exact quarter-rate period | 2 | 173 × 5,000 | 65.25 | 0.923 | 1.499 |
| Idealized smooth single-frame period | 1 | 165 × 4,096 | 44.61 | 0.480 | 0.667 |
| Idealized smooth single-frame period | 2 | 165 × 2,048 | 23.32 | 0.168 | 0.381 |
| Idealized smooth single-frame period | 4 | 165 × 1,024 | 13.52 | 0.079 | 0.258 |

The 4,096-point proxy grants a smooth single-frame layout, one folded mode, ideal alignment and fewer lifts. The twice-thinned proxy takes roughly 0.381 ms per lane and projects **0.326 s** dense savings against timing-and-carrier or **3.198 s** with the whole front end free. Its fourfold-thinned sensitivity would fit the whole-front-end allowance but represents every fourth quarter-rate delay, 16 native samples apart. A true delay can lie at eight native samples from the nearest bin, outside the frozen ±7 tolerance before noise or timing rank errors. This sensitivity also needs a new framing and resampling path. Each of these dense figures is an optimistic projection from measured component costs. No receiver-to-exit speed was measured.

## Evidence retained by the fold

The template identity holds for a prescribed weighted coherent sum, including a fixed gap mask when the original time indices remain intact. Treating gaps as excised time would change the phase. Frame-dependent gains, clipping, fractional source interpolation, independent mode powers and original normalizations carry evidence outside that coherent sum. For a common stable carrier, adding (R) equally weighted repeats multiplies coherent amplitude by (R) and independent noise RMS by \(\sqrt R\). Three individually visible frames can also cancel exactly at a mismatched residue. Empty lanes still require disqualifying unseen candidates. Multiple signed carriers can occupy the same residue, and a quantized, clipped signed cancellation residual needs its own input and confirmation. The observed relative pilot time and signed CFO cannot be taken from the raw lane's best residue for that scan. [Short verifier constraints](short-primary-fusion-profile.md#what-can-share-before-the-score-grids) · [Signed residual controls](joint-pilot-holdout.md)

The earlier differential fold accumulated conjugate lag products and discarded absolute phase. The cyclic scout used nonconjugate products and observed doubled-carrier lines with a different ambiguity. The shared-ambiguity trial granted one folded mode and compressed CFO-dependent templates into a common linear span. The current trial explicitly uses repeat-residue coherence, exact intra-period cyclic steering, and the cost of recovering signed lifts. It also grants exact delay thinning, previously applied to the released lag timing scores while retaining the original carrier path. This screen addresses the full-delay FFT bank. A sparse joint proposal that prunes lift-delay pairs from independent observable evidence would need its own cost and recall test. [Differential fold](differential-fold.md) · [Cyclic carrier](cyclic-carrier.md) · [Shared linear basis](shared-ambiguity.md) · [Earlier lag thinning](receiver-polyphase-timing.md)

The protocol stopped before waveform replay. Four tests cover opposite signed aliases with the same repeat phase, cyclic delay across an aperture gap, cancellation in a mismatched coherent residue and the declared operation and budget counts. The native FFT and exact delay decimation matched direct double-precision cyclic dot products to **2.421 × 10⁻⁶** maximum absolute error. This is a kernel consistency check. There are no new weak, dense or cancellation detection rates. [Tests](../../../tests/pipeline_eval/test_repeat_fold_bank.py)

## Reproduction

The runner needs Python, a C compiler and FFTW3f. The tests also need NumPy and pytest. The uncompressed receipt SHA-256 is `1c3065dba1c5028dc6d4ee2e4155b1adb66a16f56e83ab265193b7399c3aa9ce`. It binds the source and binary hashes, build clock, compiler, and the archived dense stage allocation. FFTW planning runs outside the timed kernel.

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -w 60 -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  timeout 90s "$release/venv/bin/python" -Bm reports.ALGO08.v3.repeat_fold_bank \
  /dev/shm/repeat-fold-reproduction
```
