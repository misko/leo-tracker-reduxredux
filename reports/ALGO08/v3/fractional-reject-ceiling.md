# The final fractional gate has no rejectable work on the measured lanes

A perfect early-rejection oracle saved **zero** on the audited saved panels. All **80** examined installed-v3 dense proposals and all **58** weak proposals passed the final fractional gate. The genuine 12 ms short verifier also passed all **34** examined weak primaries. The two empty short weak lanes failed scout confirmation and never called the verifier. Extra rejection tests would add work on these lanes. [Frozen test](fractional-reject-protocol.md) · [Measured receipt](measurements/fractional-reject-ceiling.json.gz)

## Where the negatives occur

This audit concerns the exact-versus-rolled **final fractional** verification after the original five-position integer stencil has produced a valid interior fractional vertex. It leaves coarse timing and frequency selection, signed cancellation, integer stencil ties and original gate decisions intact. Earlier pruning of coarse refinement hypotheses, short-aperture continuation, and sparse templates act before this boundary. [Earlier refinement bound](refine-bound.md) · [Short resume](resumable-primary-ceiling.md) · [Sparse template screen](sparse-template.md)

| Source | Lanes | Examined primaries / residuals | Reached fractional check | Failed final gate | Complete examined verifier CPU | Free reject oracle |
|---|---:|---:|---:|---:|---:|---:|
| Installed v3, dense DS30-0008 saved trace | 96 | 52 / 28 | 80 | 0 | 59.297 ms | 0 ms |
| Installed v3, weak DS26 saved trace | 36 | 36 / 22 | 58 | 0 | 42.941 ms | 0 ms |
| Genuine 12 ms short primary, same weak DS26 clips | 36 | 34 / 0 | 34 | 0 | 14.004–14.020 ms | 0 ms |

The original traced verifier clocks include the integer stencil and final fractional verification and exclude the I/Q load. At those boundaries the dense stock verifier used **0.618 ms per issued lane**, and the short weak verifier used about **0.412 ms per examined lane**. The installed dense panel has 44 empty lanes. None reaches the verifier. Its smallest observed final margin is **0.05143**, above the original **0.025** threshold. The weak short exercise ran three repeats on the same 18 signed ZIP clips and preserved integer epoch, fractional offset, signed CFO and both scores byte for byte against the archived results and the ordinary short primary call. No dense raw sample was opened. [Archived installed-v3 trace](measurements/scout-readout.json.gz) · [Independent signed aperture packet](measurements/eight-ms-primary.json.gz)

The dense 12 ms final factors retain no intermediate scout or gate flags. The 336-lane nonanchor ledger has 170 outputs and 166 empty lanes, so the absolute count bound on actual final rejects there is **0–166**. The complete dense recording's 11,834 short calls and 6,380 factors give **0–5,454**. The absence of a factor is insufficient to distinguish failed scout, stencil, fractional gate or final geometry. There is no measured dense short rejection rate. An upper cost bound independent of that unknown rate grants the **entire** short receiver free, including all scout and positive verification, and saves only **12.635 CPU s** on the complete dense recording. The gap to half the same historical named stock recording is **12.800 CPU s**, with all other measured spans fixed. [Complete dense acquisition](dense-full-short-raw.md)

## A valid but expensive frame-prefix certificate

For each exact or rolled template, the original 512-bin GLRT uses the squared magnitude of the sum of its 64 complex symbol products at every frequency, summed independently over frames. For template `t`, write `N(k)` for that sum and `D = Σframes (Σsymbol |z|)²` for the original normalizer. Per frame, the triangle inequality gives `0 ≤ N(k) ≤ D`. If a completed frame prefix supplies maximum numerator `M_s` and normalizer `D_s`, while the rest has normalizer at most `B_r`, then

- Exact upper score is `(M_s + B_r) / (D_s + B_r)`. The upper bound is monotone in the unseen denominator because `M_s ≤ D_s`.
- Rolled lower score is `M_s / (D_s + B_r)`. If a completed rolled correlation is nonzero, Parseval additionally supplies the universal lower bound `1/64`, since the maximum spectral bin is at least the bin average and a 64-symbol squared L1 norm is at most 64 times its L2 energy.

A rejection requires the exact upper minus the rolled lower to lie strictly below **0.025**. Passing or ambiguous cases keep all original bin candidates, ties, signed CFO and scores. A compiled certificate would also require outward rounding bounds for fractional interpolation, complex dot products and the stock FFT path, with fallback for unbounded or nonfinite states. The real-arithmetic helper is exercised against full spectral scores across all 512 bins. It does not enter the deployed gate. [Bound and receipt calculation](fractional_reject_ceiling.py)

Using only the universal rolled lower bound, even a zero exact prefix can reject only when the unseen exact denominator bound is below **4.235%** of the seen denominator. At equal frame weights, one of 8 or 15 complete frames accounts for **14.29%** or **7.14%** of the seen denominator, respectively. Thus in that equal-weight check even an otherwise ideal negative cannot omit the last frame. For the eight-frame case, even supplying the highest full rolled score seen in the stock panels, **0.05360**, as an exact oracle lower bound leaves an **8.53%** ratio limit, still below the last equal frame's weight. This is an analytical cost sensitivity, without measured per-frame energies.

For a data-dependent certificate, each unseen frame's 2,816 samples have a 15-sample Lanczos halo. A usable energy bound would scan up to **2,831 complex samples per frame**, with **5,662 component squares**, plus additions and per-symbol template/energy reductions. A conservative interpolation norm can use the maximum absolute tap weight for each lag and verify that the integer source indices are consecutive. Deviations need a padded bound or the existing verifier. A tighter rolled lower bound also needs completed control correlations and their spectrum, or weaker Parseval evidence. Evaluating the original prefix maximum on both templates requires its 128- and 512-point spectral finishing transforms. No such work is free on passing lanes. The global ADC bound avoids an energy scan at the cost of a looser enclosure. With zero answer-key savings in every traced cohort, a real certificate cannot pay any positive overhead there. A native rejection prototype was therefore stopped at this stage.

## Reproduce

Two focused tests passed. The calculation reads the existing dense trace and short ledger and only the original 18 archived weak I/Q clips. [Tests](../../../tests/pipeline_eval/test_fractional_reject_ceiling.py)

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
short=/var/tmp/leo-mixed-aperture.pdUjDb1S/build-v2
weak=/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_20_single_scan_glrt/satellite-reference.zip
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$release/src:$release" PYTHONDONTWRITEBYTECODE=1 \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 timeout 30s \
  "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.fractional_reject_ceiling \
  "$short/short-primary.so" "$short/two_carrier_receiver.c" "$weak" "$release/assets" "$fresh_output"
```
