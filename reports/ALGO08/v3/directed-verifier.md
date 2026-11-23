# Directed waveform verification on supplied timing and carrier

The installed verifier reproduced all 138 ordered factors when given the original scout's exact timing and signed CFO. Even this oracle cost **1.015 ms per matched dense factor** and **1.037 ms per matched weak factor**, including both signed scans. Fixed fractional scoring lowers that cost when an oracle also supplies the fitted fractional time. With realistic seed perturbations, the fast fixed check loses evidence, while the native refinement needed to recover it costs **1.537 ms per matched dense factor** and **1.288 ms per matched weak factor** at two proposals. The tested route does not justify another raw replay for the 2× publication target. [Build, input hashes, clocks and per-lane discrepancies](measurements/directed-verifier.json.gz)

## What the proposals supply

The study reuses the installed independent pilot gate, signed pilot cancellation, and exact-versus-rolled GLRT. The primary gate reads stereo CI16 directly. A second distinct proposal must independently confirm on the quantized signed residual after primary cancellation. Both GLRT checks use the original samples. The aperture-only loader refreshes the first 64 symbols of every possible frame with padding for the five integer centers, Lanczos support and vector reads. A candidate near the wrapped stencil boundary uses the full load. In the strict replay the aperture-only and full loads produced identical outputs, with per-lane load time falling from 0.140 to 0.072 ms on the weak slice and from 0.071 to 0.026 ms on the dense slice. The dense average includes 44 lanes where the strict oracle knows to send no proposal. [Directed native entry](../../../tools/pipeline_eval/variants/experimental/receiver_directed.c) · [Exact aperture loader](../../../tools/pipeline_eval/variants/experimental/receiver_directed_verify.inc)

The strict control traces both original scouts before final fractional verification. A forecast of the published CFO alone lacks the original oscillator input, since the published value includes the residual. The strict fixed-offset control additionally receives the final fitted fractional timing. It therefore measures scoring cost with oracle timing, rather than decoding that timing from the waveform. The guarded fixed arm reuses the earlier frame-relative fractional correlator. It falls back to absolute phase when that correlator's existing bin or margin enclosure is inconclusive. Its continuous scores can differ from installed v3. [Installed exact scoring history](../single-core-2x/receiver-fractional-absolute-score.md) · [Existing frame-relative guard](../../../tools/pipeline_eval/variants/experimental/receiver_phase_free_verify.inc)

For the independently executed seeded check, perturb each archived candidate by up to one native sample and 400 Hz in both directions, with a fixed seed. Stronger stress shifts reach three samples and 1,200 Hz. These are controlled perturbations of real measured factors, with no orbital prediction. The native runner receives only the supplied proposals, signed tuning bounds, the pilot, and I/Q. Mixed lists place the true-near proposals first and fill the remaining slots with near-frequency, shifted-time and blind decoys. The decoy-only control uses no true-near seeds, including on lanes with actual signals. A two- or four-slot bank reruns the necessary refinement on the measured signed residual. Results outside two wrapped native samples or 250 Hz from the installed factor are unmatched. That label establishes disagreement with v3, and it does not supply independent satellite truth. [Trial runner and proposal generation](directed_verifier_trial.py)

## Saved receiver results

The bounded test uses 18 DS26 weak stereo visits and the first 48 authenticated DS30-0008 visits. There were 36 positive weak lanes, 52 positive dense lanes and 44 dense lanes with no installed factor. Both slices had zero mixer-center offset. Installed v3 averaged 4.138 and 2.737 ms native CPU per weak and dense lane respectively. The candidate relinks the archived components, recompiles the timing object with site-free profile feedback, and adds generated directed examples to that feedback. The traced control reproduces all installed factor tuples before accepting any comparisons. The directed clocks cover full native calls for three alternating-order repeats, with resident I/Q and initialized plans.

The first cost column gives mean native CPU per lane with at least one installed factor. The next divides **all** measured native CPU in that configuration, including empty lanes and false proposals, by the number of matched installed factors. A lane can contribute two issued factors. Times and matches are ordered by proposal capacity 1, 2, and 4.

| Proposals and method | Slice | Positive lane CPU (ms) | All CPU per matched factor (ms) | Matched factors |
|---|---|---:|---:|---:|
| Oracle scout values, original verifier | Dense | 0.849 / 1.746 / 1.786 | 0.923 / 1.211 / 1.297 | 52 / 80 / 80 |
| Oracle scout values, original verifier | Weak | 0.829 / 1.863 / 1.873 | 0.829 / 1.156 / 1.162 | 36 / 58 / 58 |
| Oracle including fitted time, fixed exact | Dense | 0.659 / 1.445 / 1.489 | 0.728 / 1.013 / 1.103 | 52 / 80 / 80 |
| Oracle including fitted time, fixed exact | Weak | 0.658 / 1.521 / 1.563 | 0.658 / 0.944 / 0.970 | 36 / 58 / 58 |
| Oracle including fitted time, guarded fixed | Dense | 0.286 / 0.876 / 0.918 | 0.355 / 0.643 / 0.732 | 52 / 80 / 80 |
| Oracle including fitted time, guarded fixed | Weak | 0.265 / 0.919 / 0.913 | 0.265 / 0.571 / 0.567 | 36 / 58 / 58 |
| Perturbed, guarded fixed | Dense | 0.301 / 0.904 / 0.967 | 0.413 / 0.728 / 0.844 | 47 / 73 / 73 |
| Perturbed, guarded fixed | Weak | 0.283 / 0.912 / 0.968 | 0.291 / 0.597 / 0.634 | 35 / 55 / 55 |
| Perturbed, native refinement and original verifier | Dense | 1.081 / 1.991 / 2.312 | 1.361 / 1.537 / 1.873 | 52 / 80 / 80 |
| Perturbed, native refinement and original verifier | Weak | 1.093 / 2.076 / 2.385 | 1.093 / 1.288 / 1.480 | 36 / 58 / 58 |

The oracle without any filler proposals gives complete factor bytes and the sole causal selection with the original verifier. Its mean costs include zero CPU on the 44 already-known empty dense lanes. Among positive lanes alone, the oracle gives 1.561 ms dense and 1.670 ms weak with original fractional timing derivation. Providing the true fitted fractional offset as well cuts those costs to 1.246 and 1.326 ms with exact scores, or 0.679 and 0.687 ms with guarded scores. The guarded control's scores differed by at most \(7.7\times10^{-14}\) in these oracle calls.

With two perturbed proposals the guarded check matched 47 of 52 dense primaries and 26 of 28 residuals, adding seven unmatched factors. It matched 35 of 36 weak primaries and 20 of 22 residuals, adding three unmatched factors. On retained nominal matches it moved timing by up to 0.989 samples and CFO by up to 243 Hz. Independent waveform checks confirmed the supplied phase without recovering its precise value. Native refinement with two nominal proposals matched every factor within tolerance, with maximal CFO changes of 65.58 Hz dense and 97.92 Hz weak. The more stressed refinement lost one dense primary and returned one unmatched factor. The sole dense prefix selection matched within tolerance in all the two-proposal positive arms. These prefixes do not establish a full continuation or position result.

No decoy-only batch emitted a factor. On the 44 empty dense lanes these guarded calls averaged **0.098 / 0.158 / 0.270 ms** and on dense lanes containing a real pilot they averaged **0.215 / 0.538 / 0.629 ms**. Some decoys passed early confirmation and incurred signed subtraction or a final score before being withheld. For example, on two nominal guarded dense proposals, signed cancellation averaged 0.262 ms per lane overall, which includes lanes requiring none. Keeping the original gate and signed residual is material for both true and false proposals.

## Acquisition budget

The historical warm dense publication left a projected **0.633 ms per selected non-anchor factor** using prefix-extrapolated receiver CPU. In the complete DS30-0008 cold acquisition measurement, the original stereo callbacks consumed **37.3382 CPU seconds**, including 4.59412 seconds on anchors. Work outside the callbacks consumed **21.62264 CPU seconds**, for 58.96088 CPU and 99.52840 wall seconds overall. Holding those measured CPU costs and the anchors fixed, halving acquisition CPU leaves **3.26368 s**, or **0.529 ms per 6,170 selected non-anchor factors**. That CPU allowance grants all other verification and model work zero cost. Substituting the complete callback CPU in the historical 52.70-second warm acquisition model gives approximately **4.724 s** or **0.766 ms** per selected factor, conditional on the same native CPU transferring to that warm run and a 2× solver. The observed cold elapsed clock and both projected warm allowances are separate boundaries. [Complete one-core acquisition split](https://github.com/misko/leo-tracker-reduxredux/blob/7146070824b07bc3589e99d1318171fcfa3afc2e/reports/ALGO08/v3/acquisition-split.md) · [Historical anchor budget](anchor-orbit-census.md)

The budget denominator counts selected factors in the full publication. The experiment's per-matched-factor denominator includes unselected detections and thus already grants selection to every matched factor in the prefix. The byte-exact two-proposal oracle costs 1.013 ms per matched dense factor even with fitted fractional time supplied. The guarded two-proposal oracle costs 0.643 ms per matched dense factor, above the observed cold CPU allowance and near the projected warm allowance. At that rate the latter allowance admits about 7,350 matched factors, around 1,180 more than the known selected count, before paying for prediction or fallback. Perturbing the proposals consumes most of that margin and loses actual factors. Original I/Q reading and authentication still apply to every window. The combination of true-positive cost, signed residual work, rejected proposals, and unselected factors leaves too little demonstrated headroom for recording-wide prediction using the tested verifier.

## Reproduce

```sh
bench=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
release=/opt/leo-algo08/current
installed=/opt/leo-algo08/algo08v3/payload/receiver.so
weak="$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip"
binding=/srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0008.json
lock() {
  flock -x "$bench/gauss.lock" nice -n 15 ionice -c2 -n7 taskset -c 2 timeout 55s "$@"
}
lock sudo -n -u leo env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.v3.directed_verifier_trial \
  "$bench/receiver-fractional-exact-v1" "$bench/spectral-vectors-combined-v1.json" \
  /var/tmp/leo-v3-directed-new "$installed" "$release/assets" "$weak" "$binding" /srv/bulk
lock env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$PWD/src" "$tree/.venv/bin/python" -BPs -m pytest -q \
  tests/pipeline_eval/test_receiver_directed.py tests/pipeline_eval/test_experimental_receiver_fractional_exact.py \
  tests/pipeline_eval/test_experimental_receiver_tracking.py
```

The final receipt checked the candidate library digest and reused the PGO build for the repeated timing matrix. Eleven tests passed, including exact aperture reads, wrap fallback, seeded perturbations and signed factor matching.
