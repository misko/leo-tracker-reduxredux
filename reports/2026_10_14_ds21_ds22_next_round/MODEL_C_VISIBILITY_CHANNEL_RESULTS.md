# C029: visibility hypothesis rejected; channel tradeoff isolated

The native likelihood's visibility-dependent probability mass does **not** explain
the 83.390 km versus 3.691 km ranking on C029. All five sealed ambiguity endpoints
have integrated support mass one to 2.22e-16 on every training window. The summed
log-mass correction is identical (−8.88e-16), leaving every score unchanged.
No normalization change or new fit is justified by this diagnostic.

The same exact per-window likelihood replay exposes a strong channel-specific
tradeoff at the accepted shifted ordinal-1 endpoint compared with the original
incumbent:

| Channel | NLL difference, shifted minus incumbent | Signal mass, incumbent → shifted |
|---|---:|---:|
| CH1 | −47.149 | 278.128 → 296.601 |
| CH2 | +652.736 | 191.313 → 84.754 |
| CH3 | −469.921 | 269.019 → 334.757 |
| CH4 | +86.839 | 222.536 → 213.047 |
| CH5 | −139.933 | 213.333 → 246.176 |
| CH6 | +16.127 | 114.763 → 118.663 |
| CH7 | +170.894 | 271.052 → 255.108 |
| CH8 | −59.267 | 197.343 → 211.174 |

Positive NLL differences favor the incumbent. CH2's loss outweighs substantial
gains in CH1 and CH3. The net low-band NLL difference is +222.506 and high-band
difference −12.178. This identifies where the score disagreement occurs, not
which observations or assignments are physically correct. The probability mass
attributed to satellites is a model posterior, not verified detections.

Possible explanations now include a channel-specific calibration discrepancy,
different satellite assignments, or a concentration of low-quality measurements.
A useful next discriminator is a fixed-state, prespecified offset profile for
every channel, plus assignment/residual breakdown by receiver and time. Dropping
CH2 or choosing weights from its known position-error effect is not supported.

## Method and evidence

For the original uniform satellite/branch prior, integrated native density mass
is `q_clutter + (1-q_clutter)/K * sum(visible * branch_waveform_probability)`.
The Gaussian wrapped-frequency tail is negligible at the qualified sample-rate
to sigma ratio. No visibility renormalization is applied to the estimator. The
reported conditional-support score is only the original NLL plus log mass.

- All four ambiguity refinements and original incumbent included; no new selection.
- Five objective calls, five explicit orbit predictions, five per-window
  likelihood reconstructions, zero optimizer calls; complete in 14.054 seconds
  under 120/135/140-second limits. No reference or held-data access.
- Saved objective/NLL and additive channel/band scores reproduce within 1e-7.
- Source `8f2d009d5`; two tests cover actual native replay, channel/band sums,
  all-visible, one-missing-satellite and all-invisible integrated mass. Ruff passes.
- Output `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-visibility-mass-029-v1`.
- Result SHA256 `340a1bdc7f0a5dfee0702381fd2be889e653109ae3f95c025d41aa73af898de6`.
- Seal SHA256 `e828628ad65c19e1ce68cd5d712d784a1280384de27a2b8c28688fbc2c96bc98`.

This is a fitted-c diagnostic on a repeatedly inspected development case;
selected position accuracy remains 83.390 km for this source experiment.
