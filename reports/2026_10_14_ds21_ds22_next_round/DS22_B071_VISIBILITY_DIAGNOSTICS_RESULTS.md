# B071 score and rejected-fold diagnostics

The accepted full q high-origin endpoint loses **2548.359972 NLL** to the all-origin endpoint because its density numerator is worse by **2610.777434**. Its normalizer actually helps it by **62.417462**. Thus hard-visibility normalization does not explain this fixed-state ordering. No new localization fits, references or original held/locked observations were used.

| High-origin minus all-origin | Windows | Conditional NLL | log Z | −log H | Signal mass |
|---|---:|---:|---:|---:|---:|
| Full training | 2968 | +2548.359972 | −62.417462 | +2610.777434 | −535.503668 |
| CH1–4 | 1737 | +1874.414197 | −36.560470 | +1910.974667 | −388.521515 |
| CH5–8 | 1231 | +673.945775 | −25.856992 | +699.802767 | −146.982153 |
| Receiver 0 | 2121 | +1447.918379 | −44.599205 | +1492.517585 | −326.871224 |
| Receiver 1 | 847 | +1100.441593 | −17.818256 | +1118.259849 | −208.632444 |

Full-training channel NLL gaps CH1 through CH8 are respectively +763.786275, +238.309395, +924.517584, −52.199058, −256.536926, +124.364442, +323.068651 and +483.049608. CH1/3 dominate, while CH4/5 favor the high-origin endpoint. This is not a single receiver or uniformly one-band conflict. Both endpoints retain their independently fitted complete parameters; these comparisons do not isolate geography, identify actual emitters or prove the likelihood cannot find better states.

On the accepted fold0 profiles' opposite fold, high-origin loses +304.777399 NLL: low +291.393942, high +13.383457; normalizer −3.006155, numerator +307.783554. Receiver gaps are +71.795678/+232.981721. On rejected fold1 profiles' opposite fold, high-origin instead gains −239.623366 (low −191.206294/high −48.417072); this remains diagnostic only. The twofold q predictive comparison is incomplete because both fold1 fits failed strict stationarity. No diagnostic row becomes accepted merely through replay.

Visible zero-posterior odds have substantial absolute normalization leverage, but their high-minus-all full-state leverage gap is only +138.133640 (low +106.700881/high +31.432759), versus the +2548.359972 actual NLL gap. This counterfactual subtracts odds with exactly zero floating posterior and is not a normalized competing likelihood or a justification for dropping satellites. Gaussian underflow naturally produces many exact zero posteriors; it does not establish invalid candidates. Of 175112 possible full-training visible pairs, high-origin has all175112 and all-origin174989. Both accepted fold0 predictive states have all85019 possible pairs visible.

The separate derivative slice reproduced both rejected fold1 objective/NLL/fixed-XY KKT values. Neither had a visibility change at any tested coordinate/step. Common-time perturbations crossed some interpolation cells, but central objective FD at scaled1e−5/1e−6 agrees with analytic derivatives within1.5e−5. No divergent 1/h jump like the separate A053 visibility case was observed here.

| Source | Fixed KKT | Audited coordinate | Scaled derivative | Curvature | Predicted coordinate gain in ULPs |
|---|---:|---|---:|---:|---:|
| fold1 all | .001167694 | common time | +.000901105 | 588664.94 | .379 |
| fold1 all | .001167694 | strongest central nuisance | +.001167694 | 69680.16 | 5.379 |
| fold1 high | common time | −.002848607 | 427875.41 | 2.606 |
| fold1 high | .002848607 | strongest central nuisance | −.000424169 | 226677.21 | .109 |

Physical constraint minima1.257802/3.762002 confirm interior fixed profiles. Source-fold predictor rows are1441 rather than all2968 metadata/domain rows. The1e−7 objective FD becomes less accurate at the floating precision scale. These coordinate estimates support an endpoint numerical-stopping investigation; they are not coupled-Hessian certificates, automatic repairs or grounds to loosen KKT. The next approved control is both rejected fixed endpoints × original SLSQP repeat/qualified positive-tangent Newton, four extra20s/600 calls, with all four sealed before opposite-fold scoring. No automatic full FREE continuation follows.

Source/protocol `b110b99aa`, six owned tests PASS1.68s and Ruff before source freeze. Runtime `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-b071-visibility-diagnostics-v1`. Score slice completed6 objectives/6 explicit predictors/zero fits in29.165s, terminal SHA256 `49e5cbb229d43cb42e0546703ac7f0d8a91e337a5de5a1ec256ba4619a9965f7`, seal `75ed9d87b98479b0794ea7c3b88f6b318857a6e0009791b0d9cd41ab33141d48`. Derivative slice completed26/26/zero fits in29.301s, terminal `daf9e1e62c14d04ef2fecea95a3a732adf47f17718fa98a9f3ba63c1c39527a4`, seal `936cfc5a2a640725802d113b75f7781a57c45fefdd0401362bfc3e245803cee9`. Whole-slice120/135/140 bounds include preparation and source verification. Cross-fold evidence retains the disclosed full-derived discovery/frame/initializer leakage limitation.
