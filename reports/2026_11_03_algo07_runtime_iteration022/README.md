# Integer-screen qualification checkpoint

This checkpoint preserves the numerical-domain review, its recorded native
challenge results, and a guarded runtime staging tool. It does not record a
deployment or claim an end-to-end runtime improvement.

The [numerical review](NUMERICAL_DOMAIN.md) describes the admitted arithmetic
domain and selection guarantees. The [recorded challenge](receipts/domain-review.json)
covers 135 cases, 1,000,001 exact prefix values and six unsupported-input
rejections. Its largest observed error is 0.4999999998 of the calculated bound.

`tools/stage_screened_native_runtime.py` requires committed full native parity,
downstream parity, paired detector measurements, frozen policy evidence and
native/domain receipts before staging. It defaults to a dry run and does not
modify services. Full staging and installed-runtime qualification remain
separate steps; this checkpoint is not evidence that they have passed.

Validation of this checkpoint: Ruff passed for the two new tools and staging
tests; the existing and new native staging test suites passed all 30 tests.
The bounded replay launches and detector benchmarks are documented in
[iteration 021](../2026_11_03_algo07_runtime_iteration021/README.md).
