# Geometry-based eight-scan selection helps DS8/DS9, fails to transfer on DS7

Training-only information selection produces sub-km reference errors in DS8
and DS9, with better excluded-scan total scores than every individual balanced
eight-scan control in those datasets. DS7 worsens despite a larger information
proxy. Retain this as a promising but inconsistent data-selection experiment,
not a generally validated accuracy improvement.

| Dataset | Balanced-eight median reference error | Selected-eight reference error | Target score change versus mean balanced score | Versus N24 | Selected span |
|---|---:|---:|---:|---:|---:|
| DS7 | 1,416.6 m | 1,831.6 m | −80.256 | −173.739 | 10.25 h |
| DS8 | 1,422.8 m | 987.6 m | +142.290 | +15.273 | 8.01 h |
| DS9 | 1,042.8 m | 395.8 m | +128.537 | +39.680 | 11.78 h |

The balanced column summarizes three existing sets per dataset; the selected
column is one fit, not a median. These are eight scans spread over hours, not
consecutive eight-scan results. Reference errors use the exposed, unsurveyed
reference and do not establish blind absolute accuracy. DS8 is only just below
1 km. Selection itself requires the full 24-scan source pool and its existing
fit; this is a data-reduction experiment, not an eight-scan acquisition strategy.

## Frozen selection and matched fitting

The [protocol](PROTOCOL.md) preceded execution. At each dataset's existing N24
source training fit, compute centered Doppler derivatives in east, north and
scan timing for every retained candidate. Weight by training candidate and
signal probabilities times 5/70000, matching the earlier conditional information
diagnostic. Per-track constant frequency is eliminated by centering. Profile
one independent timing direction per scan using a Schur complement, leaving
a 2x2 geographic matrix.

Greedily choose eight scans maximizing the log determinant of their summed
matrix, with the fixed tiny ridge documented in the protocol. The source pool
order breaks ties. This is a local design proxy conditional on the source fit
and association weights, not the observed mixture Hessian or calibrated
covariance. It may favor biased data as well as informative data.

Refit the chosen set with the original q020 mixture using three cold starts
and three training-only timing-grid starts. Select the highest qualified
training score. All 18 starts qualify. No target score or reference error enters
scan selection, optimization or endpoint choice. The procedure is matched to
the six-start balanced controls.

## More nominal information is not sufficient

| Dataset | Information determinant ratio versus balanced controls | Weak-direction information ratio |
|---|---:|---:|
| DS7 | 1.97–2.34 | 1.52–1.88 |
| DS8 | 2.34–3.13 | 1.75–2.30 |
| DS9 | 1.72–2.30 | 1.50–1.69 |

The selected sets improve this local proxy against all nine controls, but
DS7's geographic and predictive outcomes worsen. The ratios are not accuracy
or uncertainty reductions. This is direct evidence against using this proxy
alone as a confidence or acceptance threshold.

## Excluded-scan evidence

Each selected location is scored on the five frozen outside-pool scans from
its dataset, integrating a single shared timing offset per scan under original
q020. The targets are disjoint from all 24 source scans, but have been examined
in prior experiments; they are not a new blind validation set.

DS8 wins against each individual balanced control by +112.270, +8.290 and
+306.309 total log units; DS9 by +240.010, +139.329 and +6.274. DS7 differences
are +105.962, −225.107 and −121.623. These are sums over five targets, not claims
of winning every target. The mean-score comparison in the main table averages
these three signed differences, rather than choosing the best control posthoc.

The equal per-scan mixture of the three balanced locations remains stronger:
selected-minus-mixture is −360.801, −132.861 and −70.117 for DS7/DS8/DS9. That
mixture averages different location hypotheses independently for each target
scan; it is not a single shared stationary-location fit. Keep this distinction
when interpreting its advantage. Cached control positions were checked against
the frozen outside-target manifest.

## Verification and decision

Halving derivative steps preserves the entire greedy selection order in all
three datasets. Maximum relative matrix discrepancy is 3.70e−9. Two tests check
complementary-direction selection with deterministic ties and removal of a
timing-confounded geographic direction. All optimizer gradient audits pass,
maximum discrepancy 4.97e−6. All 15 target integrals qualify without refinement;
maximum 16/32 quadrature difference is 0.001866 log units and scalar replay
error 1.82e−11. Every process exits zero in 70–81 seconds, below its 300-second
cap. Frozen source hashes and Ruff checks pass.

Do not replace the general baseline with this selector. The useful next question
is whether a training-only measure of cross-scan disagreement can distinguish
informative-but-biased scans, especially in DS7, before selection. Any such
method needs a frozen rule and fresh or explicitly exploratory evaluation;
discarding DS7's retrospectively unfavorable scans would not establish progress.

See [summary](summary.json), per-dataset outputs with all starts and selection
orders, [selection code](selection.py), and [runner](run.py). No new RF,
production changes or publication occurred. Outputs are local and use exclusive
creation. Reproduce in a fresh output context with `batch.py prepare`,
`batch.py run` under a NumPy/SciPy interpreter, then `summarize.py`.
