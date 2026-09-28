# Pilot workspace geometry cache audit

The original module was preserved before editing at
`/tmp/pilot_methods.py.before_workspace_cache` (SHA-256
`d6a599d7eb9cb4d6de5f7e6781cb6ea3ce65de422723d94ebfec9ea0a1fa4193`).
The final cache-only module is
`src/leo/analysis/starlink/pilot_methods.py` (SHA-256
`7486c61084e02b6fb61b6e1c913aaa48df487a93c235ccf4771a9ca7cc32e451`).

The change uses a bounded `lru_cache(maxsize=16)`, keyed by sample rate and
edge. Each entry contains read-only pilot geometry, exact/control template
rows grouped by symbol length, and their FP64 energies. It retains no probe
IQ, candidate, CFO, frame start, or output. The received-sample multiplication
and all reductions are unchanged; specifically, no precomputed
`conj(template) * rotation` was introduced.

## Isolated measurement

The deterministic microbenchmark generated one complex128 Gaussian 20 ms probe
per rate, warmed both implementations twice per edge, then timed 12 warm
workspace calls for each edge and used the combined median. The process was
not CPU-pinned. It ran on Linux 7.0.0-31-generic, Intel Core Ultra 9 285K
(24 physical cores), Python 3.12.14, NumPy 2.5.2.

| Rate (MS/s) | Before (ms) | Cache (ms) | Speedup |
| ---: | ---: | ---: | ---: |
| 2.5 | 1.500 | 1.437 | 1.043x |
| 5 | 2.292 | 2.189 | 1.047x |
| 7.5 | 2.308 | 2.278 | 1.013x |
| 10 | 2.679 | 2.684 | 0.998x |

Reproduce with the repository `.venv` and a deterministic NumPy generator;
load the saved module through `importlib.machinery.SourceFileLoader`, then call
`_conditioned_correlation_workspace(samples, rate, 37, 12345.0, edge=edge)`
after two warmups. The saved benchmark script and its full scanner receipts are
in this directory; use its CPU affinity rather than this microbenchmark for a
promotion decision.

The measurement supports only a small warm-call allocation/setup saving. It
does not establish an end-to-end scanner win, cold-cache behavior, target CPU
performance, or a timing-headroom claim. At 10 MS/s this measurement is neutral,
so no broader numerical optimization was attempted.

## Numerical and support evidence

An independent deterministic all-rate/both-edge comparison between the saved
module and the final module produced byte-identical exact/control correlation
values and normalized powers for selected symbols 2..65. The component test
suite passed:

```text
.venv/bin/python -m pytest -q \
  tests/analysis/test_standard_performance_equivalence.py \
  tests/analysis/test_pilot_methods_workspace_cache.py \
  tests/scanner/test_glrt64_only.py
# 69 passed
```

The new cache test covers both edges and 2.5/5/7.5/10 MS/s against the scalar
oracle, and verifies one immutable geometry entry is reused for repeated
rate/edge requests. Existing `test_shared_correlations_match_scalar_at_epoch_boundaries`
covers epoch samples `-30`, `0`, `3332`, `45000`, and `49900`, selected subsets
(16, 64, and a sparse subset), and all 300 pilot symbols. Its current fixture
uses the 2.5 MS/s lower edge; the new test extends rate/edge coverage but not
those partial-frame epochs across every rate.

## Benchmark comparison guard review

`compare.py` recursively compares the complete result object, including
decisions, candidate support, scores, and float values at absolute tolerance
`1e-12`; its tests confirm that booleans, integers, list length, missing keys,
and NaNs are not hidden by float tolerance. It also requires equal scope,
affinity, case count, raw hashes, and per-case configuration.

Before using it as a full performance promotion gate, it should also require
equal top-level backend, acquisition source hash, full-analysis mode, and a
nonempty equal measurement count. The pilot-method hash must deliberately be
different for this A/B experiment, so it should be recorded rather than
required equal.
