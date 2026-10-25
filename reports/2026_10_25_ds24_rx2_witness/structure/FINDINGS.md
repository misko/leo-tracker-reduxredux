# Complete-source structure check

The archived endpoint inspection motivated this exploratory diagnostic. It is
not fresh validation and does not change any source, A's catalogue comparison,
acceptance predicate or operational association. All three complete owners and
all 124 IDs remain intact. The [frozen design](PROTOCOL.md),
[source/input bindings](protocol02.json), [all numerical results](results.json)
and [pointwise diagnostics](point_diagnostics.csv) preserve every order and
leave-one-out calculation.

| Owner | Degree | Complete RMS, Hz | Leave-one-out RMS, Hz |
| --- | ---: | ---: | ---: |
| CH3/T002 | 1 | 752.86 | 1,022.27 |
| CH3/T002 | 2 | 62.45 | 164.67 |
| CH3/T002 | 3 | 40.87 | 330.41 |
| CH3/T002 | 4 | 21.22 | 379.73 |
| CH5/T001 | 1 | 4,790.49 | 5,092.38 |
| CH5/T001 | 2 | 535.84 | 699.37 |
| CH5/T001 | 3 | 190.40 | 301.21 |
| CH5/T001 | 4 | 20.41 | 22.81 |
| CH4/T000 | 1 | 375.22 | 399.59 |
| CH4/T000 | 2 | 262.19 | 287.02 |
| CH4/T000 | 3 | 138.28 | 152.62 |
| CH4/T000 | 4 | 70.08 | 79.13 |

Unweighted Legendre least squares uses the complete source time range for every
order. These descriptive RMS values have no fitted noise law, calibrated
likelihood or significance threshold. Hat-matrix leave-one-out residuals agree
with direct refits for all 496 point/order combinations within the frozen
1e-5 Hz arithmetic limit. No reduced dataset is passed to another experiment.
Polynomial diagnostics are independent of c; the physical catalogue test keeps
its matched c0/fitted-c arms.

## CH3: influential isolated last point, but curvature remains

The final point at **242.8192192 s** follows a **7.794739 s** gap; the source's
median gap is **0.354900 s**. It is the final/maximum-gap endpoint. Its full
native ID is
`sha256:203267ed0e2a200e420147bc8a0d6238481c3db444fa2d7c8aeee29520029eac`.
The original fast-export port reproduces its ID, measured CFO and timestamp
exactly. It comes from RX2 native receiver 1, visit 5482, probe 0, device counter
1776238111744, on the original 20 ms probe. The previous point is visit 5306,
counter 1776160164354; the counter difference exactly explains the time gap at
10 MS/s. Both are original rank-zero maximum-margin gate-passing peaks, with
fractional margins 0.230752 and 0.539648 respectively. No duplicate, wrong-channel
join or changed timestamp was found in this provenance check. Rank agreement
does not establish that different probes measured the same emitter.

The last point's leverage rises from **0.8624** at degree two to **0.99917** at
degree four. The quartic can nearly interpolate it, while predicting it from
the other points misses by **−1,855.31 Hz**. Increasing degree lowers the
complete-source RMS while worsening the leave-one-out RMS. A small complete-fit
residual therefore hides strong endpoint influence.

The endpoint does **not** generate all apparent curvature. The quadratic's
second derivative at the fixed source center is **−39.669 Hz/s²** with all points
and **−33.941 Hz/s²** in the descriptive last-point omission. Substantial
curvature survives. An incorrect graph continuation across the gap is a
plausible explanation of this endpoint behavior; these calculations do not
prove it, authenticate a different emitter, or authorize deleting the point.
The archived quadratic quality status was `no_structure_detected`; that status
does not test this independent endpoint influence.

## CH4: distributed structure rather than one tail point

The archived degree-four graph already has `structure_flagged` with adjacent
residual correlation **0.82347**. The independent complete polynomial reproduces
its 70.08 Hz RMS and correlation; leave-one-out RMS is 79.13 Hz. Maximum quartic
leverage is **0.3662**, and final-point leverage is **0.3478**, far below CH3's
near-unit endpoint leverage. Ordered quartic residuals have a nine-point run of
one sign, and their largest adjacent change is about **99.36 Hz** across a
1.416 s interval. The [saved adjacent summary](adjacent_summary.json) retains
all four orders and exact IDs for these changes.

The behavior is consistent with unresolved smooth structure or a graph join
across different frequency paths; it does not isolate either mechanism. A
single endpoint explanation is inadequate for the distributed residual pattern.
An imperfect polynomial family can also leave correlated residuals. Neither
correlation nor a polynomial fit diagnoses receiver bias, orbit error or true
identity by itself.

CH5 is different again: degree-four RMS is 20.41 Hz and leave-one-out RMS
22.81 Hz, with adjacent correlation 0.203. Its smooth complete-source behavior
does not validate the old rejected physical label, whose archived residual RMS
was 2,442.51 Hz. The new ordinary catalogue comparison must retain that outcome
separately.

![Complete-source quadratic residuals and four-order RMS diagnostics](polynomial_structure.png)

## Execution and limits

Two owned numerical tests pass, including direct leave-one-out closure on an
irregular design and invariance to a uniform CFO gauge shift. The successful
run takes **1.111 s**; a conservative cumulative processing bound including the
failed setup and tests is **3.112 s**, below 30 s. The first setup incorrectly
called the public persistent-timing adapter on a fast wrapper whose embedded
timing is absent. It stopped before polynomial calculations. Version 02 uses
the original fast-export `frequency_evidence` port instead; prior source,
protocol and failure are retained in `preparation01/` and [failure01.json](failure01.json).

No orbit propagation, new physical-candidate scoring, position fit, GPS/IQ
processing, source modification or policy change occurs. These are small
historically selected diagnostics. Their strongest use is to explain why a
complete-source physical hypothesis can fail and why a lower polynomial RMS
does not justify association or point deletion.
