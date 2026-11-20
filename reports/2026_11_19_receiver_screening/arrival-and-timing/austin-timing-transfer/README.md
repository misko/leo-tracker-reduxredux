# Does a fifth timing proposal recover more shifted Austin RF?

**Stock four, the waveform-derived fifth center, and a half-frame sham recovered exactly the same targets at every power setting.** The real fifth added search support on 15 of 20 mixtures, including all eight weakest mixtures. In those weakest cases, its hints were 3,019–5,464 samples from the known target phase. Allowing the extra center preserved stock search points and did not recover those targets. [Paired chart](timing-transfer.png) · [All matched counts and timings](transfer-scores.csv) · [Frozen test](PROTOCOL.md)

| Austin excerpt power relative to roof background | Any gated correct phase and CFO, each of the three methods | Correct highest-margin observation, each method | Other passing target-lane candidates, stock / fifth / sham |
| --- | ---: | ---: | ---: |
| −24 dB | 0/4 | 0/4 | 8 / 7 / 8 |
| −18 dB | 0/4 | 0/4 | 7 / 6 / 7 |
| −12 dB | 4/4 | 3/4 | 6 / 6 / 6 |
| −6 dB | 4/4 | 4/4 | 4 / 4 / 4 |
| 0 dB | 4/4 | 4/4 | 10 / 10 / 10 |

The phase-only and joint phase/CFO recovery counts were also identical in this roster. The −12 dB result exposes a ranking distinction. Every method produced one correct passing candidate for all four mixtures, while one correct candidate lost the highest-margin selection. Across all 20 mixtures, exact-phase and folded-CFO recovery occurred in 12 for each method, with 11 correct winners. The fifth removed two off-target passing candidates relative to stock across the 20 target lanes. Those candidates can be genuine roof detections. The unaffected lane contributed six passing candidates per strength in each method. [Per-edge and per-source interval rows](transfer-scores.csv)

All three recovered 4/4 clean transplanted controls and issued correct highest-margin observations in each. No Austin waveform was present in the two roof-only controls. One of those dual windows had passing original roof candidates under all three methods. Every call preserved the four stock regions and their local maxima. A null fifth reproduced stock candidate payloads byte-for-byte. An actual fifth addition covered 27 additional epoch cells and retained 19 extra coarse proposals across the 20 mixed target lanes. The half-frame sham added 60 cells and retained nine extra proposals. Those are search counts, with the 0.025 verification gate reported separately. [Native candidate, hint and regional telemetry](native-outputs.jsonl.gz)

## Measurement boundary

The only Austin source was the same 50 ms channel-6 excerpt. The test displaced two disjoint 20 ms source intervals on both measured subbands. Four predetermined epoch shifts spanned 878–6,866 samples and frequency shifts spanned −55.352 to −16.190 kHz. The shifted measured IF includes Austin background energy as well as the desired signal. The named levels refer to full-window relative power against the unchanged roof recording in the receiving lane. A second genuine roof lane remained byte-identical. The authenticated channel-6 donor windows were DS29-0519 lower visit 157 and DS26-0162 upper visit 77. Each strength reuses the same four edge/interval combinations from one Austin capture. [Known shifts released after prediction](truth-after-lock.json) · [Archive, donor and stock/scout library seals](source-lock.json) · [Primary Austin waveform paper](https://arxiv.org/abs/2602.02627)

The statistic requires phase within 2 samples at 10 MS/s and CFO within 1 kHz modulo the symbol alias, both after the genuine target is recovered through blind acquisition. The outcome is relative localization-phase support, with no independent position, absolute receive UTC, calibrated carrier, or causal orbit fit in this excerpt. The earlier direct recovery study supplies physical code-order evidence before mixing. [Direct Austin waveform qualification](../austin-waveform/README.md)

Native median host CPU by mixed input was 26.34 ms for stock four, 32.14 ms for the fifth including its FFTW scout, and 33.12 ms for the sham including its scout. The median paired fifth-minus-stock cost was 6.10 ms. Times cover detector and scout after IF extraction and mixing, with three rotated-order calls per input. The data show no additional admitted Austin timing support in this small matched test. [Prediction seal](prediction-lock.json) · [Score seal](score-lock.json) · [Stage seal](stage-lock.json)

To replay, use `python -m tools.pipeline_eval.qualification.austin_timing_transfer /path/to/exemplar250-257.zip` with a fresh `--out` containing `PROTOCOL.md`, followed by `python -m tools.pipeline_eval.qualification.austin_timing_figures --out ...`. This uses the previously authenticated host stock, fifth-union and FFTW binaries and both cached roof IQ windows. The source authenticates all assets before running any acquisition.
