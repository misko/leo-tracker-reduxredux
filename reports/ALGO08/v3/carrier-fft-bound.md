# Bounding carrier FFTs in the two-scan scout

The 2,048-bin bound could omit full FFTs at **170 of 1,968** carrier-search rows on the saved weak physical and southern simulated slices. Even with perfect reuse of the shorter transforms, the modeled carrier FFT saving was **5.7%** and **3.2%** respectively. The 1,024-bin bound omitted zero rows. The carrier search is too small a share of acquisition for this mechanism to advance the single-core target materially.

ALGO08v3 takes two independent 4,096-point carrier FFTs at each of 12 proposed timing epochs. Each transform receives 704 nonzero input slots at quarter rate. Each epoch contributes its two best eligible bins, subject to the circular carrier exclusion around the first bin. The four highest normalized scores across the epoch rows feed the full-rate refinement. The signed-cancellation scan repeats the same search with freshly estimated modes. [Frozen timing object and stage profile](../single-core-2x/receiver-spectral-vectors.md)

For each epoch, let \(F(\theta)\) contain the two complex carrier spectra and let \(D\) be the original normalization denominator. Multiplying both spectra by \(e^{352i\theta}\) preserves their joint norm and puts their polynomial frequencies between −351 and 352. Project this vector onto its unit direction at the maximum, and take the real part. That gives a real trigonometric polynomial of degree at most 352 with maximum equal to the original vector norm. Two polynomial inequalities give upper bounds on every normalized carrier score, including those in every admitted signed band. The tighter bound uses either the Ehlich–Zeller inequality or the summation-kernel estimate of Jetter, Pfander and Zimmermann.

\[
  \max_{\theta} \frac{\|F(\theta)\|^2}{D}
  \le \frac{\max_{0\le j<N} \|F(2\pi j/N)\|^2}{D}
  \min\left\{\frac{1}{\cos^2(352\pi/N)},\frac{N}{N-704}\right\}
\]

With 2,048 anchors the multiplier on coarse power is about 1.36. With 1,024 it is 3.20. Both grids cover the whole period and include anchors outside the eligible carrier band. This makes the enclosure conservative at band edges and across FFT wrap. The frozen minimum bin separation and exact signed-band eligibility still determine the two seeds in each fully evaluated epoch. [Approximation-theory derivation](https://www.mathematik.uni-marburg.de/~pfander/pubs/crestfactor.pdf)

The audit first reveals both exact seeds of an evaluated epoch. It can omit the remaining work on another epoch only when its upper bound is strictly below the fourth exact score revealed so far. Exact ties retain the frozen order. The raw scan can also suggest two nearby epochs to evaluate first in the residual scan. Raw rankings never supply a residual bound or a score, so a weak or newly revealed carrier keeps its full residual search whenever the residual data leave it competitive. Signed subtraction, timing proposals, refinement, all independent confirmation gates, fractional scores and continuation run on the original paths in the audit.

This calculation supports a mathematical DFT bound. The trace extracts coarse anchors from the already evaluated frozen FFTs to estimate selectivity. An implementation with shorter FFTs needs an allowance for both Float32 transforms and power rounding and must verify any overlapping rank interval with the original arithmetic. The audit explicitly counts violations of the ideal envelope on frozen output. Its FFT counts measure opportunity, with every trace lane still executing both original scans if eligible.

## Saved waveform audit

The exact relink and the traced copy reproduced the ordered factor bytes and continuation results on all **116 lanes**, including 48 primary and 22 residual factors. Both slices generated zero selected continuation observations. All examined bounds covered the measured full-grid peaks. Every evaluated order reconstructed the exact top four seeds, including tie order, on each of the 164 scouts. The southern prefix supplies simulated geographic development evidence. The 18 physical archive visits were selected previously for weak-carrier challenges.

| Slice and scan | Carrier-search rows | Full rows after 2,048 anchors | Full rows with two timing-first seeds | Full rows with two raw-hint seeds |
|---|---:|---:|---:|---:|
| DS26 weak primary | 432 | 371 | 371 | — |
| DS26 weak residual | 432 | 394 | 396 | 396 |
| Public south primary | 960 | 898 | 901 | — |
| Public south residual | 144 | 135 | 136 | 135 |

The raw-hint order reduced the number of full evaluations by one on the southern residuals relative to the timing-first control. The weak-carrier residual counts agreed. The 4,096-bin FFT can be represented mathematically as two 2,048-bin phase branches. In the ideal reuse model, every omitted full row pays for one branch and avoids the second. If the shorter FFT has to be followed by an independent frozen full FFT, the best 2,048-bin schedule for each row in the table adds 24–33% modeled transform work under the \(N\log_2N\) arithmetic model. Even ignoring all bookkeeping, this direct fallback spends more than the original carrier FFT search. Model figures are arithmetic comparisons. The audit collected no performance clocks or position results.

The trace library SHA-256 is `a2e1ae030a1b070fd6fca2d34526f4f1612eaaae176185f7534466e7eefb1b07`. The full receipt, including individual I/Q digests and the ordered packet digests, is `/var/tmp/leo-algo08v3-carrier-bound.json`, SHA-256 `a00c64e73bc0a99d209fd0d0eb2d507d61fe8c93dff5612be14e4c099683fc7d`. Five component tests passed, spanning off-grid modes, hidden and equal-score seeds, wrapped hints, and full fallback.

## Budget

The archived timing implementation used by v3 spends 61.60 ms across 432 carrier searches, about 143 µs per scout on the DS26 profile. Even two scans per lane through the entire 9,288-probe DS30-0374 example would put roughly 2.65 CPU seconds in the complete carrier search at that rate. The budget for v3 acquisition on warm successful recordings calls for saving about 21.5 s on average. The rate extrapolation uses the saved profile's scout mix as a model. It excludes read, decimation, mode construction, lag search, refinement, cancellation, verification and publication. [Carrier stage clocks](../single-core-2x/receiver-spectral-vectors.md#exact-vector-arithmetic-around-the-two-mode-scout-ffts) · [V3 timing targets](single-core-target.md)

## Reproduce

Run from this checkout. The audit relinks the archived ALGO08v3 receiver and verifies its release digest. It then recompiles only the timing source with a trace hook and checks factors and continuation against the relinked library. The remaining commands use saved I/Q and one low-priority Gauss core. No recording or position solve is launched.

```sh
bench=/tmp/leo-algo08v2-2x-bench
main_tree=/home/mouse9911/gits/leo-tracker-reduxredux
assets=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c/assets
weak_archive="$main_tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip"
public_panel=/tmp/leo-regional-qZJKBw4W/public/panel.json
audit_work=$(mktemp -d /var/tmp/algo08v3-carrier-bound.XXXXXX)
lock() {
  flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 OMP_THREAD_LIMIT=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=src:. timeout 50s "$main_tree/.venv/bin/python" "$@"
}
lock -m pytest -q tests/pipeline_eval/test_receiver_cfo_peak_bound.py
lock -m tools.pipeline_eval.variants.experimental.receiver_cfo_peak_bound \
  "$bench/receiver-fractional-exact-v1" "$audit_work/trace" "$assets" \
  "$weak_archive" "$public_panel" > "$audit_work/receipt.json"
```
