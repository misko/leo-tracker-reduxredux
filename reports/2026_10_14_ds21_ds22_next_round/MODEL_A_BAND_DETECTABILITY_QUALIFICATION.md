# Band-specific detectability: actual-data qualification

The new objective passes zero-fit qualification on the current full-band
DS21-035 and DS21-053 states. No localization improvement is asserted.

The model uses separate bounded satellite-detectability coefficient vectors for
CH1-4 and CH5-8. Their weighted mean retains the original shared prior; their
difference receives a unit Gaussian penalty. Both effective coefficient vectors
retain the original [-2, 2] bounds. The high-band fraction is fixed from the full
training observation inventory across masks. Original physical, calibration and
timing priors are counted once. The visibility width is fixed at 1e-5.

With the two coefficient vectors equal, objective, likelihood and posterior
responsibilities exactly reproduce the smooth shared-detectability model.
Physical and original nuisance gradients, and the sum of the two coefficient
gradients, agree within 8.45e-12. This nesting is with the smooth model, not the
hard visibility model.

| Case | New coefficients tested | Maximum central-difference error | Wrapper objective calls |
| --- | ---: | ---: | ---: |
| DS21-035 | 108 | 1.648e-7 | 219 |
| DS21-053 | 116 | 1.247e-7 | 235 |

All new coefficients were tested at a deterministic nonzero band contrast,
strictly inside their bounds, using central steps of 1e-4. The maximum allowed
absolute discrepancy was 3e-4. Actual-data physical gradients were checked by
nesting only; the separate small-fixture component test checks every coordinate
at nonzero contrast and a smooth horizon transition.

The run used 454 wrapper objective evaluations and zero optimizer calls in
15.883 seconds. Each full band-specific objective evaluates its two band
children; wrapper counts must not be interpreted as native orbit-call counts.
No reference positions or locked inputs were read. Source states are
initializers, not claimed stationary endpoints of the new model.

Eight component/qualification tests passed; Ruff passed. The model source is
`ab9100f7a`; the qualification driver is `c1f8630e0`.
Immutable receipts and archived source are under
`/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-band-detectability-qualification-v1`.
Result SHA-256:
`8f82df279d31aa7f14ff1e8874752321ae8a2c55d6f50a3ce5a3986e62b3502b`.

Next evaluation: matched blocked predictive comparisons against the smooth
shared model, with identical candidates, physical seeds and search budgets.
Better in-sample fit alone will not establish better localization or justify
cohort promotion. Existing cohort histograms remain unchanged by this check.
