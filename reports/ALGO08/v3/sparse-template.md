# Sparse pilot templates over a full signed visit

The best 16 linear spectral lines retain **3.55–3.74%** of the quarter-rate pilot-template energy. Searching signed CFO with those lines took **0.166–0.180 ms per scout**, with timing, anti-alias filtering, and verification still to do. The measured cold callback allowance leaves **0.138 ms per scout** after the existing oracle confirmation path. Increasing line count to recover more information exceeds even the more favorable warm budget. The direct sparse-tap bank also exceeds the search allowance under its optimistic instruction model. [Prespecified screen](sparse-template-protocol.md) · [Energy curves, signed controls and native clocks](measurements/sparse-template.json.gz)

## Prior work and the change tested

The earlier interleaved anchor census already priced a recording-wide route with stock acquisition on anchors and shifted verification on other visits. Its idealized fallback needed about 63% of baseline acquisition CPU even when verification was free. The calibration-independent timing brackets and waveform visit pool also left substantial gaps in new and secondary carriers. Those routes reduce how many independent searches are attempted. This study keeps the whole time aperture in every scout and measures how sparse the exact pilot itself can be. [Sparse anchor census](anchor-orbit-census.md) · [Timing brackets](../single-core-2x/receiver-brackets.md) · [Waveform pooling](visit-pool.md)

The direct low-bit experiment compressed full tap banks. The cyclic-carrier comb ranked lines of a quadratic pilot product, and the shared ambiguity experiment measured complete inverse rows for a low-rank linear bank. The present comb uses original linear complex-template Fourier lines over the entire 20 ms visit. The time-domain screen selects individual taps by the same fixed pilot power, using no site, lane or waveform labels. [Low-bit bank](low-bit-pilot.md) · [Cyclic carrier comb](cyclic-carrier.md) · [Shared linear ambiguity span](shared-ambiguity.md)

## Retained information

For a known timing and CFO in proper white noise, the ratio of the best sparse matched-filter SNR to the full matched-filter SNR equals the selected fraction of template energy. The largest tap powers give the best coordinate subset. For an orthogonal DFT the same argument applies to the largest spectral line powers. The quarter-rate time arm measures template energy after the original FIR. Actual post-filter noise can be correlated, so that arm's fraction describes template geometry under the white-noise model.

The time masks use the installed 64-symbol early refinement aperture and repeat the same coordinate set on 14 complete origins. The native aperture contains 2,816 taps per frame. The quarter-rate aperture contains 704. Selecting the strongest 16 quarter-rate taps retains 9.65–11.31% of energy, versus 0.79–0.90% for a uniformly spaced 16-point mask. Selecting 128 retains 48.14–49.40%. Half energy requires 131 and 137 taps at the lower and upper edges. Ninety percent needs 408 and 422. On the native aperture those levels require 544–551 and 1,654–1,686 taps, respectively.

The spectral calculation transforms the full periodic synthesis waveform at 10 or 2.5 MS/s. The quarter-rate sensitivity grants free access to every fourth raw sample and includes its aliases. For the most favorable energy-ranked subset at that rate, the strongest ideal matched timing sidelobe beyond eight native samples has **36.4–40.4%** of main-peak power at 16 lines. A uniform 16-line mask among spectral bins above one millionth of peak power retains 0.17–0.27% of the full energy and has almost unit sidelobes on this cyclic template. With energy ranking, half of the quarter-rate energy still requires 510–511 lines and 90% requires 1,688–1,701. These are template measurements. They carry no measured weak-factor recall. [Audit code](sparse_template_trial.py)

## Cost of a sparse search

A deliberately coarse independent-frame bank grants 1,667 timing cells, 357 signed carrier cells and one imaginary vector operation for an entire complex tap packet at each cell per frame. Even a one-packet mask takes **0.347 ms per scout** across 14 frame origins at four such operations per cycle and 6 GHz. Four real sign products raise that count to **1.389 ms**. The independent-frame bank preserves broad gain and phase flexibility but uses the coarse CFO spacing only within each frame.

Superposing all 20 ms coherently changes the signed-grid requirement. Even a 50 Hz grid retains only 40.5% coherent rectangular-window power at the midpoint between bins. With that grid and one free phase-aligned accumulation per cell, the same optimistic direct model gives **2.223 ms per scout**. Both direct models grant free tap gathering, normalization, ranking and all independent checks. They apply to the stated cell-by-cell packet bank. A different search that factorizes or omits cells can have different work.

The factorized spectral floor reads the full visit, executes a complex FFT, forms powers, and streams shifted contiguous spectra into 32,001 signed CFO scores at 50 Hz spacing. It uses the installed template's line strengths as weights. This CFO-first pass discards line phase for ranking and returns no absolute timing. A complete sparse matched search would also need absolute timing, independent gain and phase treatment and a second search after signed cancellation. The measured native boundary includes CI16 unpacking and the native score accumulation, with reused FFT plans and free ranking. [Native clocked entry](sparse_template_comb.c)

| Line count | Quarter-rate pilot energy retained | Native CPU ms/scout at 10 MS/s | CPU ms/scout with free quarter-rate input |
|---:|---:|---:|---:|
| FFT alone | | 0.656–0.681 | 0.127–0.132 |
| 16 | 3.55–3.74% | 0.802–0.824 | 0.166–0.180 |
| 32 | 6.36–6.60% | 0.835–0.864 | 0.196–0.225 |
| 64 | 11.26–11.29% | 0.899–0.964 | 0.256–0.302 |
| 128 | 19.15–19.30% | 1.038–1.064 | 0.369–0.446 |

All four strong synthetic signed positives rank first at each line count and both strides. The seeded noise also emits four ungated proposals per lane. The experiment does not assess verified false alarms. The clock is the median across nine repeats and both signed lanes for each edge. The stored assets have no role in selecting controls from a recording.

The complete native callback budget across the original 13,530 dense lanes is **0.581 ms/lane** in the measured cold acquisition CPU model or **0.689 ms/lane** in the earlier warm elapsed projection. The 148/96 native scout ratio translates those to 0.377 and 0.447 ms/scout with all subsequent processing free. Charging the already favorable guarded original-sample control at 0.368 ms/lane reduces the scout allowances to **0.138 and 0.208 ms/scout**. That control already knows empty lanes and uses oracle fitted time and signed CFO. The 16-line lower-rate floor alone exceeds the cold budget. Its nominal warm headroom is 28–42 µs for everything omitted. The installed matched dense front-end FIR alone measured 152 µs per scout. That separate clock prices the original anti-alias stage if retained. [Acquisition split](acquisition-split.md) · [Guarded confirmation allowance](shared-ambiguity.md) · [Matched decimation profile](receiver-polyphase-timing.md)

With the favorable budget already exhausted by the native direct and full-rate spectral paths, and little information or downstream headroom in the quarter-rate sensitivity, the trial stopped before opening raw weak and dense waveforms. This rules out the tested paths under the stated callback bounds. An adaptive sparse transform, a different way to nominate only a subset of lag-frequency cells, or a new independent verifier would need its own costs and quality evidence.

## Reproduce

```bash
bench=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
lock() {
  flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 40s \
    env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH="$PWD:$release/src:$release" "$@"
}
lock "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.sparse_template_trial \
  "$new_work" "$release/assets" > "$new_receipt"
lock "$tree/.venv/bin/python" -BPs -m pytest -q tests/pipeline_eval/test_sparse_template.py \
  tests/pipeline_eval/test_shared_ambiguity.py
```
