# Native band states: signal–clutter reassignment drives the score gaps

The fixed-state audit of DS22-109 and DS22-131 identifies large, structured signal-versus-clutter differences. Changing one global clutter-odds multiplier from one quarter to four times its original value **never reverses either paired ranking**. Visibility normalization is negligible here; extra alias-branch reassignment is also negligible. This does not establish which satellite assignments are physically correct.

Both cases used their prespecified low-origin and high-origin **complete CH1–8 states**, including the repaired strict low-origin131 state. “Low-origin” and “high-origin” describe initialization ancestry, not half-only fits. Frozen reused comparison keys `full_minus_half_nll`, `full_signal_mass` and `half_signal_mass` mean **low-origin minus high-origin**, low-origin mass and high-origin mass respectively. They are not a new full-versus-half position comparison.

| Case | Lower-band NLL gap | Upper-band NLL gap | Total NLL gap | Prior gap | Objective gap |
|---|---:|---:|---:|---:|---:|
| 109, low-origin minus high-origin | −1532.375 | +3160.602 | +1628.227 | +74.402 | +1702.629 |
| 131, low-origin minus high-origin | −5100.759 | +198.348 | −4902.411 | −61.110 | −4963.520 |

Lower NLL/objective is preferred. These are same-model, same-bank comparisons. The independently reconstructed native conditional row scores, satellite/clutter posteriors and once-counted priors closed against the supplied objectives; posterior discrepancy was zero, NLL discrepancy at most3.64e-12 and integrated-mass discrepancy at most2.22e-16. No reference or held data was read.

## The discriminating windows

For109, the high-origin state's upper-band signal mass is1192.847 versus721.361 at the low-origin state. **514 windows** change from low-origin clutter to high-origin signal, contributing **+3428.105** to the low-minus-high NLL gap—more than the net upper-band gap after opposing contributions. Both receivers contribute: RX0 +1627.313 and RX1 +1533.289. All four upper channels favor the high-origin state; CH6/7/8 contribute +770.116/+1061.891/+1208.837. Eight of nine fixed30-second blocks favor it. The largest increase in candidate signal mass is satellite52650 (+180.246), followed by56023 (+90.908). The five largest positive candidate-mass differences total386.303 against a net471.486 increase. Candidate-mass change is not an exact causal allocation of the nonlinear likelihood gap.

For131, the repaired low-origin state's lower-band signal mass is1465.658 versus723.547 at the high-origin state. **746 windows** change from low-origin signal to high-origin clutter, contributing **−5078.120** to a net lower-band gap of−5100.759. This is overwhelmingly RX0 (−5144.164); RX1 opposes by only+43.405. Every lower channel and all nine fixed30-second blocks favor the low-origin state. Candidate-mass gains are distributed across multiple satellites:63950 +110.067,58212 +93.333,59900 +88.052,59325 +80.313 and64082 +68.561; the top five total440.327 against a net742.111 increase.

Branch-level versus satellite-marginal posterior overlap differs by less than1e-18 in these comparisons. Thus the observed disagreement is not primarily between retained native alias branches of the same satellite. Posterior overlap is0.568 overall for109 and0.595 for131;131's lower-band overlap is only0.434, versus0.829 for its upper band.

## Clutter sensitivity is negative within the declared range

The fixed clutter mixture probability is0.238095238; the corresponding native density floor is9.523809524e-8 Hz⁻¹ at2.5MHz. These are distinct quantities. The cached conditional-density calculation changes clutter odds while retaining each endpoint's physical prediction, satellite propensities and branch evidence; it recomputes the matching visibility normalization. No parameter is fitted or selected.

| Clutter-odds multiplier | 109 total conditional NLL gap | 131 total conditional NLL gap |
|---:|---:|---:|
| 0.25 | +1909.592 | −5893.789 |
| 0.5 | +1768.857 | −5398.134 |
| 1 | +1628.227 | −4902.411 |
| 2 | +1487.593 | −4406.713 |
| 4 | +1346.810 | −3911.292 |

The global-odds test does not support fitting a global clutter repair next. It does not rule out observation-conditioned acquisition selection. In109 integrated mass is effectively one. In131 the low-minus-high difference in summed log normalization is only+0.423089, far below the4902-unit likelihood gap.

## Residual and temporal evidence: useful limits

Posterior-weighted residual RMS spans76–141Hz at band level against the fixed125Hz Gaussian width. Per-band signed means are nearly zero, as expected after calibration fitting; that is not evidence that calibration is physically correct. Thirty-second residual means remain structured, reaching about107Hz in magnitude. Residual calibration remains a possible contributor, but the decisive likelihood differences involve windows that one state discards as clutter, where its signal-weighted residual summaries supply little evidence.

Consecutive same-receiver/channel observations within1second have identical MAP labels on1341/1548 versus1329/1548 edges for109, and1577/1718 versus1593/1718 for131. Both competing states can therefore form persistent patterns. These observations do not establish true tracks or violations of independence. Prior negative temporal controls on DS21-039 and B059 further argue against adding generic persistence merely because assignments differ.

## Next discriminating prototype

The strongest next test is **acquisition-conditioned signal/clutter support with one coefficient**, rather than another global-odds, histogram, propensity or persistence expansion. First verify an existing public detector-strength field and its definition/provenance. If available, a single coefficient can modulate window-specific clutter log odds from that measured covariate, with zero coefficient exactly nesting the current conditional native model. Share the coefficient across receivers and bands; preserve the full existing satellite-propensity and calibration priors. Do not interpret a detector margin as a calibrated probability.

Use fold-only covariate scaling and a matched original-versus-one-coefficient predictive test at both declared origins. Report opposite-fold likelihood and the fixed-parameter density-substitution effect separately from optimization changes. The earlier native empirical-background CV already found density gains without resolving geographical preference; repeating that histogram is not the proposed experiment. Conditioning on an acquisition statistic may itself reflect selection/collider effects, so this remains a conditional observation model, not a demonstrated generative detection probability. The field qualification must precede any numerical fit. A calibration extension ranks second, pending independent residual evidence; generic temporal persistence ranks lower given the counterevidence above.

## Receipts

Source/protocol/tests: `edaf44a70`; five component tests passed, including actual native models with and without common clocks and nonzero shared/contrast coordinates. Root's cached clutter helper is `9e273d5ce`. Ruff passed.

Exactly **four full objectives and four extra explicit orbit reconstructions**, zero optimizer calls, were used across the two cases. Each full objective internally evaluated its two band-child densities. The two-worker wave completed in42.096seconds; per-case internal elapsed times were31.982/36.111seconds under120/135/140-second bounds. All cached odds multipliers used existing details without additional objectives or orbits. No source outcomes were changed or retried.

Evidence: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-native-band-state-audit-v1/{DS22-109,DS22-131}/run/result.json`. Full candidate, receiver/channel and time-block partitions are retained there. Result SHA256s:109 `abe0ef516ec4af2f01bc0521a185b6ef84eeb6c2a79cbc5a9403f661bd9abe12`;131 `f8f19f637ed209f5b8c7a7f25517853da4fd83bdfd6c6150497b53fa95eed3ef`.
