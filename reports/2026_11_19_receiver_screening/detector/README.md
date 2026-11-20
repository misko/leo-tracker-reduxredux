# Adjoint fractional GLRT64

Moving Lanczos interpolation into the two pilot templates reduced continuous refinement CPU by 42.6% and full detector CPU by 3.14% on the fresh blocks. It passed the prespecified timing gate at 1.74× continuous-stage speedup. The tenfold stage target was unmet. [Protocol](PROTOCOL.md) · [Qualification](qualification.json)

## Where time remained

The locked stack combined spectral coarse and repair, the fine-frequency FFT, the revised conditioned bank, and fused final GLRT. On segment 3 visits 1536 and 1538, coarse scoring and repair consumed about 0.195–0.385 CPU seconds per visit. It remained the largest stage at roughly 56–66% of full detector CPU. Fine FFT was 48–75 ms on warm calls and continuous refinement fell inside a 23–36 ms fractional GLRT boundary. The complete fine-frequency grid keys were distinct within each receiver, including the producer’s wider-anchor retry. There was no measured fine-grid reuse from exact duplicate keys.

The existing coarse decomposition still computes roughly 33.6 million sliding tone outputs and 48.8 million anchor magnitudes per receiver and default search. Pruning this work by sampled anchor scores requires a tighter enclosure than the sum of available contributions. With only the normalized per-anchor bound of one, the upper bound remains at least `1 − m/N` after `m` of `N` terms, even when all evaluated terms are zero. The eighth retained coarse score was 0.1694–0.1732 in the eight profiled default receiver banks. This particular bound cannot exclude cells below that cutoff until it has evaluated at least 82.7–83.1% of their terms. The new refinement targeted repeated tap work where a transposition preserved the search and every positive factor. [DS26 coarse envelope](DS26-0036-coarse-envelope.json) · [DS29 coarse envelope](DS29-0082-coarse-envelope.json)

## Transposed sampler and guard

In the original method, each rotated matched template sums 44 samples, and each fractional sample is a 16-tap Lanczos sum. Transposing that operation convolves the original 44-tap coefficients with the common 16-tap weights once for each exact and rolled symbol. A 59-tap dot product then evaluates each correlation directly against raw IQ. Both paths keep the same samples and guard support. At 15 frames, the old interpolation forms 675,840 complex-by-real weighted terms per candidate before its matched correlations. The new symbol dot products use 113,280 complex-by-complex terms plus the shared template convolution. A complex-by-complex term costs more arithmetic than a real-weighted term. The measured stage includes the remaining autocorrelation, normalization and fallback work.

Binary rounding of absolute sampling coordinates can give the incumbent slightly different Lanczos weights at different frames. The observed raw IQ maximum and template L1 norms bound the resulting complex correlation error. The code also budgets absolute phase and FP64 operation error. From that bound, it encloses both normalized GLRT spectra. It reruns the original fused scorer if an exact-spectrum bin cannot win uniquely or if the fractional margin interval could reach 0.025. Negative continuous fields can differ by roundoff even when their reduced spectra certify the same frequency bin and decision.

## Held-out IQ results

Each table entry covers four previously unopened raw visits. The held-out total includes 48 timed detector calls per mode, three per visit. Both runs used one numerical thread and separate pinned performance cores, 2 for DS26 and 3 for DS29.

| Recording and block | Median full CPU, locked → adjoint | Full CPU summed, locked → adjoint | Continuous CPU summed, locked → adjoint |
| --- | ---: | ---: | ---: |
| [DS26 early](DS26-0036-early.json.gz) | 0.506 → 0.488 s | 6.152 → 6.016 s | 0.185 → 0.118 s |
| [DS26 late](DS26-0036-late.json.gz) | 0.438 → 0.403 s | 5.503 → 5.360 s | 0.184 → 0.117 s |
| [DS29 early](DS29-0082-early.json.gz) | 0.516 → 0.516 s | 6.431 → 6.526 s | 0.246 → 0.125 s |
| [DS29 late](DS29-0082-late.json.gz) | 0.501 → 0.395 s | 5.898 → 5.330 s | 0.214 → 0.117 s |
| Combined |  | 23.984 → 23.232 s | 0.829 → 0.476 s |

The measured continuous CPU reduction accounts for 1.47% of the locked full CPU. Zero continuous work would save at most 3.46% if the other measured stage costs stayed constant. The rest of the measured 3.14% whole-detector difference includes timing variation outside the revised stage. One raw block was slightly slower in full CPU despite a faster continuous stage. Peak traced allocations rose by approximately 0.12 MB on DS26 and 0.05 MB on DS29. The listed candidate work arrays peaked at about 0.30 MB.

All 20 archived development and held visits matched the installed capture-era payload in the locked control. The adjoint preserved every rank, timing, CFO, integer score, gate and positive fractional factor. All 126 changed held candidate rows and 25 changed development rows were below the fractional gate. Their only changed fields were fractional exact and rolled-control scores and derived margins. The maximum change was `1.46e-13`. Over all held repeats, 429 continuous calls ran the adjoint and 60 used the fused scorer because the margin might reach the positive gate. The development data also exercised a genuine ambiguous frequency-bin fallback. [DS26 controls](DS26-0036-development.json.gz) · [DS29 controls](DS29-0082-development.json.gz)

The strong and faint plants recovered epoch 731 on both receivers in both recordings. Empty IQ and the independent noise controls produced no positives. Adjacent-CFO mixed pilots retained the same positive winners, including their original continuous scores. All synthetic checks passed the same field-level contract. The component test forces both a near tie and a margin interval crossing the gate.

## Fresh partial-IQ positions

Each fresh v5 run used eight valid held IQ visits and archives for the other visits. The DS26 composite used 6,757 archived valid visits and changed negative raw scores in 15 receiver probe rows. DS29 used 4,860 archived valid visits and changed negative raw scores in 16 probe rows. Both composites matched every positive factor, prepared observation, track and final satellite owner in the complete capture-era archive control. The trial and control worker requests verified their separate input hashes and matched all scientific settings. Both position and RF fit outputs matched exactly in each calibration arm. [Positions](positions.jsonl.gz) · [Matched archive controls](control-positions.jsonl.gz)

| Recording | Geographic error `c0` / `fitted_c` | Conditional Doppler RMS `c0` / `fitted_c` | Fresh fit CPU / wall |
| --- | ---: | ---: | ---: |
| DS26-0036 | 1.278365 / 1.208143 km | 74.760916 / 74.682298 Hz | 144.56 / 161.10 s |
| DS29-0082 | 0.566947 / 0.517230 km | 97.003569 / 96.683622 Hz | 108.49 / 118.10 s |

Median geographic error across the two cases was 0.922656 km for `c0` and 0.862686 km for `fitted_c`. The interpolated 95th percentiles were 1.242794 and 1.173597 km. The frozen causal settings, positive factors and search budgets matched across the calibration arms. [Position-error distributions](error-distributions.json) · [Figure data and input seal](prediction-lock.json)

## Reproduction

Run `tools.pipeline_eval.qualification.fractional_adjoint_eval` with the appropriate `--case`, `--split`, and `--out`, the capture-era producer first on `PYTHONPATH`, all numerical runtime thread counts set to one, and the corresponding CPU affinity. Use `tools.pipeline_eval.qualification.fractional_adjoint_position --gate --report <directory>` to verify the sealed stage. Fit the same partial-IQ bundles with `--case` and `--work`, then run `--package` and `--seal-figures`. The expanded fit work for this run is under `/srv/bulk/leo-dev/fractional-adjoint-position-20261119-zh0OYR`.
