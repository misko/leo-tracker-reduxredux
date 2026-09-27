# Lag-4 phase-CFO blind-acquisition prototype

This isolated research prototype evaluates the single experiment frozen in
`../native/NEXT_EXPERIMENT.md`. It leaves the deployment sources and every
previous native artifact unchanged.

The common detector's differential coarse stage already computes a complex
lag-4 correlation at local timing cells, then discards its phase. The candidate
uses that phase to enumerate every carrier alias inside `[-400, 400] kHz`. It
scores exactly three conditioned cells around each alias at offsets `-100`,
`0`, and `+100 Hz`, then runs the unchanged five-cell timing lattice,
fractional fit, and full-support exact/control GLRT.

`build.py` verifies the frozen FP64 V4 build receipt and all of its sources,
generates the minimal transformed sources under `_generated/`, and builds a
separate shared library. Generated-source hashes and the parent V4 receipt hash
are stored in `libphase_cfo.so.build.json`.

The strategy fallback was frozen before the full run:

- no candidate or a fractional-incomplete phase result invokes an independent
  packed FP64 V4 blind call, and both calls are charged;
- a complete margin-negative phase result remains the detector result;
- the independent comparison call never seeds or repairs the strategy.

`run_experiment.py` processes all 256 development receiver-visits and 24
supported constructed receiver-controls. It alternates reference-first and
strategy-first timing order over five repetitions after one warmup. IQ loading
and hashing are outside the timed call; receiver selection, packing where
required, native calls, and strategy fallback are inside it. The runner refuses
to overwrite `results.json` and never selects holdout cases.

Run the component checks with:

```sh
.venv/bin/python -m pytest -q \
  reports/2026_09_27_ds5_cached_tracking/phase_cfo/test_phase_cfo.py
```

The experiment is rejected. See `REPORT.md` for the immutable result.

