# DS5 decision-band experiment

This experiment tests a causal, anti-aliased 2.5 MS/s decision stream followed
by the existing native whole-dwell GLRT. It treats native 2.5 and 5 MS/s runs as
matched-rate comparators. The 7.5 and 10 MS/s results report synthetic filter
fidelity, known candidate coordinates, and throughput only; they make no recall
claim because this environment has no native-rate GLRT oracle for those rates.

The FIR has 40 output samples of causal startup support and 20 output samples
of group delay. Results zero the incomplete startup support, require another
two decision samples for the fractional search, and subtract group delay when
mapping the confirmed timing back to source coordinates. Baseline-relative
retention requires a candidate detection plus CFO agreement within 8 kHz and
circular 750 Hz-lattice timing agreement within 2 microseconds.

Create a development configuration, evaluate development, then freeze the JSON
before validation:

```bash
python decision_band.py init-config --output config.dev.json
python decision_band.py evaluate \
  --dataset ../dataset/cases.json \
  --split dev \
  --config config.dev.json \
  --reference-root /home/mouse9911/gits/leo-adaptive-position-deploy \
  --output development.json
```

Evaluate the separate synthetic detector controls with `--split control`.
The CLI accepts `--split holdout` so the final authorized evaluation can use
the identical frozen source and config. Holdout IQ must not be opened during
development or validation.
