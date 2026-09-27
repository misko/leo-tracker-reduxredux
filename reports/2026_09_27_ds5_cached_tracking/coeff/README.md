# Fractional coefficient-transpose GLRT prototype

This directory contains one bounded research prototype for the final,
full-aperture known-state GLRT. It does not change the deployment or the frozen
native tracking prototypes.

For a fractional epoch, the reference GLRT first interpolates each received
sample with a 16-tap Lanczos kernel and then correlates the result with each of
64 pilot symbols. The prototype transposes those two linear operations. It
builds pilot coefficients for each distinct observed interpolation pattern and
dots those coefficients directly with the CI16 sample workspace. Exact and
control pilots use separate coefficients. The integer-epoch path calls the
unchanged reference implementation.

The table key is the actual base-shift and fractional pattern observed at each
sample, plus the early/late region. This matters at floating-point binade
boundaries: nominal epoch fraction alone does not determine every rounded
sample position. Tables live only for one measurement invocation. The builder
caches the Lanczos weights and normalizer for repeated *exact* fractions while
constructing that invocation's tables, then discards all tables. Consequently,
the recorded candidate timing charges coefficient construction for every
visit; it has no hidden warm persistent cache.

Files:

- `design.json` freezes the scope, tolerances, timing protocol, and stopping
  rule before controls and development-oracle measurements.
- `coeff_glrt.c` and `coeff_glrt.h` implement the research C port.
- `coeff_glrt.py` builds the hash-pinned shared library and exposes the narrow
  Python binding.
- `test_coeff_glrt.py` covers both supported rates and receivers, fractional
  boundary cases, CFO endpoints, integer routing, bounds, and input
  immutability.
- `run_experiment.py` runs constructed controls and the existing same-visit
  development oracle. It never reads holdout IQ.
- `results.json` is the row-level immutable receipt.
- `REPORT.md` records the decision and limitations.

The component checks are:

```sh
python3 -m pytest -q reports/2026_09_27_ds5_cached_tracking/coeff/test_coeff_glrt.py
python3 -m py_compile \
  reports/2026_09_27_ds5_cached_tracking/coeff/coeff_glrt.py \
  reports/2026_09_27_ds5_cached_tracking/coeff/run_experiment.py \
  reports/2026_09_27_ds5_cached_tracking/coeff/test_coeff_glrt.py
```

In a clean copy where `results.json` does not yet exist,
`python3 reports/2026_09_27_ds5_cached_tracking/coeff/run_experiment.py` builds
the pinned library and writes the receipt. The runner refuses to overwrite an
existing result.

