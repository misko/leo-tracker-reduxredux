# Real ACF-only exclusions are uncommon at the current parent; no blanket gate change

The normalized-ACF issue occurs on real curves, but this audit does **not** find
the nearly zero residual regime that rejected the noiseless synthetic controls.
Across all 24 usable DS24 fast scans, only **2 of 296 current unowned excluded
curve/arm records** fail ACF alone under the observed legacy track predicates.
Both are c=0; their fitted-c counterparts also fail other predicates. Their
conditional residual RMS is **40.38 and 22.63 Hz**, versus millihertz-scale fitted
residuals in the noiseless synthetic panel. No gate or threshold was changed.

![Historical and current rejection categories, and real ACF-only amplitudes](acf_evidence.png)

## Historical flags and current exclusions are different populations

The archived initial graph snapshots contain **1776 curved nomination rows**.
Of these, **929 have incompatible nomination flags**. Recomputing the original
stored-innovation screen and saved RMS/bias predicates gives:

| Archived incompatible snapshot category | Rows |
| --- | ---: |
| ACF only | 54 |
| ACF plus other failures | 559 |
| Other failures without ACF | 316 |

The historical ACF-only residual RMS ranges from 25.11 to 153.14 Hz, median
42.65 Hz. These old flags are not current-parent rejection decisions. Only
four of those 54 sources remain wholly excluded from curved calibration and
unowned in both current parent arms; labels, calibration and selections can
change between states.

Source review found a potential archival caveat: `nomination_rows` can overwrite
candidate/scalar fields while retaining copied residual vectors from another
association choice. We checked rather than assumed the bindings. **All 929
incompatible rows here have zero feasible candidates and stored residual RMS
matching their scalar RMS**, so none of this rejected subset was removed for
that ambiguity. The historical classification still concerns those saved
vectors and observed predicates, not a new identity/visibility search.

At each unchanged current saved parent position/reference, we reconstructed
complete accepted IDs, including postfit extensions. There are **152 whole
curved sources excluded from calibration**. Four intersect accepted IDs in at
least one arm, leaving **148 unowned sources / 296 matched arm records** for
the primary current comparison:

| Current unowned source category | c=0 | Fitted c | Total arm records |
| --- | ---: | ---: | ---: |
| ACF only | 2 | 0 | 2 |
| ACF plus other failures | 77 | 78 | 155 |
| Other failures without ACF | 69 | 70 | 139 |

No current unowned record passes all observed primitives. These are repeated
arm evaluations, not 296 independent curves. Partially retained sources,
linear-only sources and alternate nominees are outside this current panel.

## The two current ACF-only examples

| Source at saved c=0 parent | Points | Conditional RMS | Supplied median sigma | ACF / original limit |
| --- | ---: | ---: | ---: | ---: |
| 0019 RX2 CH4 T000, modeled53038 | 43 | 40.38 Hz | 99.29 Hz | 0.684 / 0.610 |
| 0095 RX2 CH5 T001, modeled68382 | 40 | 22.63 Hz | 57.52 Hz | 0.645 / 0.632 |

Both fail profile and conditional ACF. All other observed c=0 primitives pass.
Under fitted c, the same sources additionally fail conditional mean and
quadratic tests, with conditional RMS 271.43/252.83 Hz; profiled RMS remains
38.70/22.73 Hz. Thus waiving ACF alone would not produce a paired curved-gate
pass at these fixed states. Target-local constants and evidence roles matter;
this is not a claim that a valid predictive model or later refit must fail.

The supplied sigma values are unchanged pre-existing per-ID noise proxies.
We did not fit a noise scale to any rejected target, use its residual scatter
to declare it insignificant, or select an amplitude cutoff. RMS/sigma ratios
are descriptive: the two c=0 values are 0.407/0.393. A small ratio does not
establish white residuals, a correct identity or acceptable position influence.
The supplied sigma itself is not externally calibrated noise truth.

## Limits and decision

Current replay fixes the saved parent position, phase reference, proposed
identity and alias. It uses conditional mean residuals and existing track
predicates. It neither searches target phase/identity nor integrates full
target-local nonlinear phase, fragment and unsupported physical-orbit
uncertainty. No unsupported orbit calibration is enabled. Therefore the other
294 failing records do **not** establish that 148 identities or sources are
wrong, nor that a covariance-aware predictive treatment could not change a
result. The inherited graph/source selection and all prior geographic exposure
also remain; this is not untouched validation or a false-rejection-rate study.

Keep the gates unchanged. ACF-only historical flags are not a large ready pool
of current safe additions, and the real amplitudes differ substantially from
the deterministic synthetic edge case. If revisiting the statistic, first test
its false-rejection/false-admission behavior under a predeclared supplied-noise
model and structured alternatives, keeping other gates and paired ownership
requirements. Do not infer an amplitude waiver from these two examples or
start another recovery campaign. Identity/discrepancy and evidence-role checks
remain more direct next work.

All 24 cases completed in **160.78 seconds**, within a 300 s one-worker compute
cap, with **zero position fits**, no GPS, no new RF and no candidate search.
Two owned classification/boundary tests pass. Evidence is in
[summary.json](summary.json), [historical.json](historical.json),
[current_parent.json](current_parent.json), [case denominators](cases.json),
[input/output seal](seal.json) and [small report/test receipt](report_receipt.json).
