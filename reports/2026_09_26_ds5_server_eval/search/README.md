# DS5 server-side GLRT search

This directory contains a bounded saved-IQ experiment. It never opens radio
hardware, changes production code, or treats a blind GLRT result as truth.
The comparison endpoint is candidate identity retention relative to the exact
blind 512-screen control: a candidate must pass `fractional_complete` and
`margin > 0.025`, then match the baseline within 8 kHz CFO and 2 us circular
fractional epoch in the same selected 20 ms window.

The development search compares direct 512 seeding, two rate-specific
high-resolution timing grids, a three-seed union, and blind fallback policies.
The existing binding supports only 2.5 and 5 MS/s. Cases at 7.5 and 10 MS/s
are listed as unsupported without loading or resampling their IQ.

Run the component tests with:

```sh
python -m unittest reports/2026_09_26_ds5_server_eval/search/test_run_experiment.py
```

Once the dataset exists, run development with:

```sh
python reports/2026_09_26_ds5_server_eval/search/run_experiment.py \
  --split dev \
  --config reports/2026_09_26_ds5_server_eval/search/development_search.json \
  --output reports/2026_09_26_ds5_server_eval/search/dev_results.json
```

Run the separately labelled synthetic controls during development with
`--split control` and a separate output. Pilot/noise/tone outcomes remain
separate in the summary. The constructed noise and tone cases are useful for
detecting new gates relative to the blind control, but they do not establish a
calibrated false-positive rate.

Validation and holdout reject the development configuration. They require a
`stage: frozen_validation` configuration selected and hashed after development.
Holdout additionally requires `--authorize-holdout`; this experiment does not
run it as part of development or validation.

For tracking, the safe causal design is acquisition first, then a cache keyed
by `(channel, edge, receiver)`. Store only a gated candidate's absolute phase
`(source_start_counter + window_offset + epoch + fractional_offset) mod frame`
and propagate that phase to the next visit using its source counter. A gap,
counter discontinuity, channel change, stale age, or failed seeded confirmation
must trigger blind reacquisition. The present 8-visit split blocks are useful
only if a key repeats; tracking state never crosses session-disjoint splits.
