# Frame-relative pilot correlation in fractional verification

Precombining the pilot and frame-relative carrier oscillator reduced verifier CPU by **29%** and complete native CPU by **4.6–5.0%** on a chronological physical prefix. Across **588 lanes**, the experiment reproduced all **388 exported factors**, including **120 second-scan factors**, and all **53 continuation selections**. It kept exact rank, integer and fractional timing, signed CFO and strong-margin classes. The continuous scores changed on 260 lanes, by at most **1.97×10⁻¹³** in exact-pilot score and **7.41×10⁻¹⁴** in rolled-control score. These score differences change byte-level detection digests. [Matched receipts](receiver-fractional-phase-results.json)

## Correlation and numerical safeguards

The coarse refinement and its independent gate already precombine pilot and oscillator. The final fractional verifier in the frozen packed receiver returns to absolute sample coordinates for Lanczos interpolation and carrier rotation. It evaluates the oscillator at every tap in every complete frame, applies it to the interpolated I/Q, and then multiplies by the exact and rolled pilots. This stage and the integer timing stencil together consumed about 18.5% of the packed receiver profile. [Packed verifier profile](receiver-stencil.md)

A constant carrier phase for one complete frame multiplies its symbol vector by a unit complex scalar. Each contribution to the GLRT power spectrum and the magnitude normalization is invariant to that scalar. The prototype calculates a common frame-relative oscillator and precombines it with both pilot references once across frames. It reduces roughly 40,000 sine and cosine evaluations to 2,816 for a typical fractional factor. The per-tap correlator then needs two complex products across the two references. Fractional Lanczos positions, weights and accumulation order follow the original absolute coordinates. Both scouts, signed cancellation, integer timing stencil and fractional peak interpolation stay on the frozen path.

Reordering those products and omitting the per-frame phase changes floating-point rounding. The alternate path estimates a per-frame perturbation using the maximum rounded Lanczos weight sum, the pilot L1 norms, the CI16 component limit and an allowance for absolute and relative phase evaluation. The allowance is (128\epsilon(1 + 2\pi |f|N/F_s)) in FP64, with (N=200{,}000). The score radius accounts for both the spectrum power and its normalization. For per-frame correlation error (E), (F) frames and the observed spectrum ceiling (C), it uses (u=E\sqrt{F/C}), (v=2u+u^2), and (4v/(1-v)+10^{-11}) when (v<0.25). Larger bounds or inadequate normalization require the original full calculation. This is a conservative engineering allowance for the measured floating-point implementation, including the libm and FFT behavior.

The verifier also returns to the original calculation when the interval can cross the factor gate at 0.025, the published strong-margin count at 0.1, or the top two frequency bins in either spectrum. If two exported margins can change order, it recomputes both through the original verifier before ranking them. The diagnostic route keeps the original score computation. The measurements observed **17 fallbacks in 391 attempted final fractional calculations** and no two-carrier ordering retries. Tests cover signed planted pilots on both antennas and byte-identical stock recomputation on a low-amplitude ambiguous spectrum. The saved slices leave the two-carrier ordering retry unexercised.

## Matched native calls

| Existing slice | Lanes | Factors / residual factors | CPU saved over packed receiver |
| --- | ---: | ---: | ---: |
| Physical prospective archive | 160 | 141 / 55 | 4.9–5.4% |
| Physical weak-carrier challenges | 36 | 58 / 22 | 7.1–7.8% |
| Public northern simulation prefix | 80 | 25 / 2 | 3.6–3.7% |
| Public southern simulation prefix | 80 | 12 / 0 | 1.1–1.6% |
| DS30-0016 chronological prefix | 232 | 152 / 41 | 4.6–5.0% |

The prospective stage profile covers two repeats and 282 complete verifier calls. Verifier CPU decreased from **0.2360 to 0.1675 s**, while complete native calls decreased from **1.2329 to 1.1649 s**. The chronological slice used the first 128 scheduled visits of DS30-0016 and retained 116 through the existing quality policy. Its 53 selected observations all had the same continuation rank and signed measurements. The public prefixes are geographic development simulations. The trial does not compare position or publication.

## Reproduce

The pinned 950c receiver is the reference. The candidate adds `--phase-free` to the packed build. The reference rebuilt byte for byte, and the candidate rebuilt to SHA-256 `18d09cbc0ec16012c33ca1986adb23feabcc67658e2674d95ee6fe44d8916e4f`. Both receive full I/Q on both resident antennas. The saved comparisons alternate native call order over visits, lanes and two repeats.

```bash
algo08_work=/tmp/leo-algo08v2-2x-bench
algo08_python=/home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python
algo08_native=tools.pipeline_eval.variants.experimental
algo08_assets=/opt/leo-algo08/current/assets
algo08_pilot_archive=/srv/bulk/leo-dev/ds26-two-carrier-20261120/prospective-iq.zip

algo08_lock() {
  flock -x "$algo08_work/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
    env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONPATH=src timeout 80s "$@"
}

algo08_lock "$algo08_python" -m "$algo08_native.receiver_build" \
  "$algo08_work/receiver-phase-free-guard.so" --pack-stencil --phase-free
algo08_lock "$algo08_python" -m "$algo08_native.receiver_phase_trial" \
  "$algo08_work/receiver-stencil.so" "$algo08_work/receiver-phase-free-guard.so" "$algo08_pilot_archive" \
  /home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_11_20_single_scan_glrt/satellite-reference.zip \
  /tmp/leo-regional-qZJKBw4W/public/panel.json --assets "$algo08_assets"
algo08_lock "$algo08_python" -m pytest -q \
  tests/pipeline_eval/test_experimental_receiver_phase_free.py \
  tests/pipeline_eval/test_experimental_receiver_stencil.py
```

The separate stage profile adds `--profile` to both builds and runs `receiver_benchmark` with `--visits 80 --repeats 2` on the prospective archive. The chronological comparison passes `list(receiver_brackets.read_physical(binding, Path("/srv/bulk"), 128))` for DS30-0016 to `receiver_phase_trial.compare` in the release environment. All four component tests passed.
