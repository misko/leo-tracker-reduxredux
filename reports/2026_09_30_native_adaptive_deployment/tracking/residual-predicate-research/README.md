# Exact residual-predicate pushdown research

This experiment moves existing admission predicates before two
`circular_residual` calls in `candidate_segments`. After isolated qualification
and physical review, the four-line change was applied to production tracking;
all goldens remain unchanged. It has no algorithm, threshold, ordering, fit,
cache, identity or tie-policy change.

The initial scan now rejects unavailable or underweight points before the
residual. The refined scan additionally rejects points strictly before
`initial.start_s` or strictly after `initial.end_s`. That condition is the exact
complement of the previous inclusive
`time_s >= initial.start_s && time_s <= initial.end_s` admission condition, so
the endpoints remain included.

The residual vectors are private to `candidate_segments`. Each is read by
`one_per_source` only at indexes already appended to `raw` or `refined_raw`.
An index is appended only after its residual has been calculated. Skipped cells
therefore cannot be observed. Every admitted residual retains the same
expression, point visitation order and binary64 inputs. Validated inputs and
spacing are finite, with positive spacing, so the skipped calls do not provide
error handling used by the result contract.

Host and ASan/UBSan `test_tracking` and `test_chosen_point` pass. A causal
support-end comparison of every five-second prefix is exact for all 60 prefixes
and retains aggregate serialization SHA-256
`e9642606acf84a8b4e4817ec082a0381ac51857afb8950cca8ec68cca0014108`.
The final control and candidate serializations both have SHA-256
`6819cb39151bb2cbe894e5d427244aa95d1eae73e17469e5033659d2b0a30084`.
The rebuilt production source also passes host and ASan/UBSan component tests,
including the focused unavailable, underweight, outside-window and inclusive
start/end boundary regression. Its independent 60-prefix comparison is exact.

On the final 11,747-candidate prefix, identical counter instrumentation records
15,120,503 residual calls for the control and 4,402,243 for the candidate, a
70.89% reduction. One uninstrumented `perf stat` run per binary records
5,856,190,833 combined hybrid-core cycles for the control and 4,761,390,899 for
the candidate, an 18.69% reduction. Task clock fell from 595.10 to 476.90 ms.
The host was shared, so this is a material diagnostic result rather than a
latency qualification or distribution.

`production.patch` preserves the exact reviewed delta and excludes the
research-only call counter. The production source now has SHA-256
`b8f2dff142a190622de5299e229b0ff82c5fe2aa465e386957496dfc8115b1c5`.

Root-owned CPU-only physical ABBA evidence records control serial full-prefix
times of 27.8324 and 27.7599 seconds and candidate times of 26.2104 and 26.2147
seconds, a repeatable 5.57–5.83% improvement with all four outputs byte exact.
This is a serial standalone reconstruction benchmark. It is not the two-worker
publication path, a five-second publication qualification, or a concurrent
capture/search measurement. See `physical-arm/receipt.json`. This agent did
not access hardware or RF.

Reproduce the builds from the repository root:

```sh
bash reports/2026_09_30_native_adaptive_deployment/tracking/residual-predicate-research/build.sh \
  control host reports/2026_09_30_native_adaptive_deployment/tracking/residual-predicate-research/build-control
bash reports/2026_09_30_native_adaptive_deployment/tracking/residual-predicate-research/build.sh \
  candidate host reports/2026_09_30_native_adaptive_deployment/tracking/residual-predicate-research/build-candidate
bash reports/2026_09_30_native_adaptive_deployment/tracking/residual-predicate-research/build.sh \
  candidate sanitize reports/2026_09_30_native_adaptive_deployment/tracking/residual-predicate-research/build-sanitize
```
