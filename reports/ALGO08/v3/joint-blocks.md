# What primary pilot block dots retain after cancellation

For a known timing and signed CFO, a complex dot and a template norm per cancellation block recover the fitted gain. An alternate candidate needs a separate raw dot against its own template. Even an exact model of the primary subtraction and the complete raw frame covariance leave that alternate dot undetermined. An integer regression fixture produces identical block dots, raw means and raw covariance for two inputs, then gives different shifted-pilot power and residual covariance after cancellation. [Audit](../../../tools/pipeline_eval/variants/experimental/receiver_joint_blocks.py) · [Component tests](../../../tests/pipeline_eval/test_experimental_receiver_joint_blocks.py)

## Conditional statistics

Write `x` for raw signed I/Q, `P` for the matrix with the confirmed pilot's disjoint block templates, and `a` for their complex least-squares gains. The unquantized residual `r = x − Pa` obeys `Tᴴr = Tᴴx − (TᴴP)a`.

This is an exact update for a bank `T` whose complex raw dots were already computed. Given the primary dots `Pᴴx`, one can recover `Tᴴx` for templates in the column space of `P`. Within that space the ideal cancellation already gives `Pᴴr = 0`. Selecting candidates after cancellation can change `T`, including both timing and CFO.

Stock uses signed 16-bit `r_q = Q(x − Pa)` with nearest-even rounding and clipping. For integer inputs away from half-integer boundaries and the rails, the signed correction is `round(Pa)`. At half-integers the translated tie depends on raw integer parity. At a rail, the correction depends on the original sample. Finite precision also matters near a rounding boundary. The true integer correction `d = x − r_q` yields `Tᴴr_q = Tᴴx − Tᴴd`, which still needs both dots. [Signed cancellation](../../../native/algo08v2/tools/pipeline_eval/variants/pilot_cancel.c)

Let `X` and `D` be the raw and correction frame matrices after the common linear mixer, FIR, row selection and row-centering operations. Before normalization the new Gram is `XXᴴ − XDᴴ − DXᴴ + DDᴴ`. The diagonal supplies the residual row norms. The raw Gram and modeled `DDᴴ` leave the mixed `XDᴴ` undetermined. Recomputing the residual top-two eigenspace changes the time streams that feed the quadratic lag scores. This algebra uses ideal linear operations. The released mixer and FIR round in Float32, and stock timing re-estimates all 12 epochs on the actual signed residual. [Frozen timing and carrier path](../single-core-2x/receiver-spectral-vectors.md)

The carrier score also divides by the energy of the selected mode segments, and the lag score uses within-epoch lag-product energy. A whole-row covariance supplies neither interval denominator. Those denominators and the lag cross-products need their own statistics if a replacement chooses to keep the frozen score.

## Saved and generated results

The four entries first by recording and visit in the sealed DS26 weak archive supply eight stereo lanes. Two generated stereo windows contain an equal-amplitude, opposite-CFO pair on one lane and a weaker carrier 19 kHz away from the primary at the same epoch on the other lane. They cover both pilot edges and opposite 50 kHz mixer centers. The trace reproduced all **18 ordered factor records** byte for byte. Native v3 returned both carriers on the opposite-CFO lanes and withheld the weaker 19 kHz companion on both edges. [Input hashes and lane measurements](measurements/joint-blocks.json)

| Measure | Archived weak | Generated |
|---|---:|---:|
| Primary / residual factors | 8 / 4 | 4 / 2 |
| Energy of alternate pilot templates in primary block span | 0.0920–0.1947% | 0.0892–0.0922% |
| Residual matched energy retained using only primary dots and true signed correction, as a fraction of full residual matched energy | 4.25e−8–2.16e−7 | 4.19e−9–4.34e−9 |
| Smallest singular value between raw and residual top-two covariance bases | 0.136–0.900 | 0.252–0.552 |
| Shared quarter-rate timing phases out of 12 per scout | 0–5 | 2–9 |

The energy figures use the native confirmed residual timing and signed frequency. The second energy row grants the audit the exact signed correction and replaces `x` with its orthogonal projection into the primary span. Almost all measured residual evidence comes from the omitted raw complement. All six verified residuals had a nearby raw seed within seven wrapped native samples and 4.55 kHz on this slice. That coverage statistic alone leaves open whether a fixed raw candidate bank could suffice elsewhere. [Earlier raw shortlist misses](../single-core-2x/receiver-shortlist.md)

Across 4.8 million ADC components the ideal model had no clips or exact half ties. Both `Q(x − Pa)` and `x − round(Pa)` reproduced all signed CI16 components. Rounding moved samples by 0.2864–0.2869 ADC counts RMS. In a double-precision mixer and FIR diagnostic that isolates quantization, the updated ideal and signed CI16 normalized covariances differed by 4.89e−5–1.63e−4 in relative Frobenius norm. The direct ideal covariance agreed with the Gram identity to 2.80e−11 maximum entry difference. The larger raw-to-residual basis rotation comes from removing the pilot and remains even when the quantization correction is small.

## Operation and timing ceiling

At fixed geometry the frozen covariance builds 105 upper-triangle frame dots over 4,740 complex quarter-rate samples, about **498,000 complex multiply-accumulates**. A direct mixed update takes 196 frame dots over the same width, about **929,000**, even if the correction-only Gram were free. The comparison is a count for the straightforward dense update. A structured mixed operator would need its own measured cost and evidence.

A literal full signed candidate bank on 3,333 timing phases and 2,621 carrier cells has about **8.74 million** candidates. With one early 128-symbol projection per frame (1,408 quarter-rate samples) across 14 frames, direct evaluation takes about **172 billion complex multiply-accumulates** and storing those complex Float32 dots takes **0.98 GB per lane**. Per-block dots would use more storage. These counts describe direct evaluation and storage. Transform or compressed banks may share work, and must show the retained candidate support.

The prior dense prefix leaves **1.260 ms per lane** for the entire acquisition resident path to save 20 seconds at 13,530 lanes. Even making cancellation free at the older measured rate of **0.744 ms per reached cancellation**, and assuming every lane reaches it, projects to **10.07 CPU seconds**. A block representation must eliminate more than residual synthesis, and a complete two-carrier representation also has to maintain the independent pilot gates and original-I/Q exact verifier. These costs are projections from the earlier stage profiling. [Dense budget and cancellation profile](differential-fold.md)

## Reproduce

The runner uses the saved reference and timing trace from the earlier carrier FFT audit. It verifies the archive's SHA-256 for every used window and requires identical ordered factor bytes from the traced and frozen libraries. A standalone native cancellation must reproduce the original residual timing rows and carrier seeds on each evaluated lane. [Trace build](carrier-fft-bound.md)

```sh
bench=/tmp/leo-algo08v2-2x-bench
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
main_tree=/home/mouse9911/gits/leo-tracker-reduxredux
native=/var/tmp/leo-algo08v3-carrier-bound-run
flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:. \
  timeout 25s "$main_tree/.venv/bin/python" \
  -m tools.pipeline_eval.variants.experimental.receiver_joint_blocks \
  "$native/reference.so" "$native/trace.so" "$release/assets" \
  "$main_tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip"
```
