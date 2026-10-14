# B059 full-training propensity block gaps

The two-objective, zero-fit audit passed in12.949s after source `2b76e4fe4` and owned tests/Ruff were frozen. It replays the two accepted free propensity endpoints from the eight-call full-training experiment, without changing B's original folded-frequency physics, model, bank, calibration or training observations. Original held/locked observations and references are untouched. Positive gaps below favor the incumbent.

The nearby endpoint's full-training conditional-CFO NLL disadvantage409.666440 is low-band loss549.928821 offset by high-band gain140.262381. There are1550 low and972 high windows. Near/far signal masses are678.846/781.467 in low and553.480/560.055 in high; the corresponding clutter masses are871.154/768.533 and418.520/411.945. This is not an undifferentiated all-band loss.

|20s bin | Windows | Full near−far NLL | Low | High | Opposite-fold CV near−far | Both CV fits accepted |
|---:|---:|---:|---:|---:|---:|---|
|0 |223 |57.564 |22.753 |34.812 |87.852 |true |
|1 |163 |−64.470 |−47.231 |−17.240 |−48.893 |false |
|2 |180 |−69.975 |−93.841 |23.866 |−54.636 |true |
|3 |184 |44.250 |35.437 |8.813 |160.425 |false |
|4 |232 |163.389 |124.681 |38.708 |−348.990 |true |
|8 |205 |398.713 |211.137 |187.577 |41.943 |true |
|9 |217 |444.846 |215.605 |229.241 |312.681 |false |
|10 |208 |220.385 |199.406 |20.979 |265.328 |true |
|11 |203 |35.661 |122.355 |−86.694 |18.130 |false |
|12 |224 |2.328 |31.099 |−28.771 |14.140 |true |
|13 |234 |−355.695 |−179.518 |−176.177 |−503.802 |false |
|14 |249 |−467.330 |−91.953 |−375.377 |−796.667 |true |

There are eight adverse and four favorable observed bins. Bins8/9 contain422 windows and favor far by843.559196; bins13/14 contain483 windows and favor near by823.024809. Both contribute substantial opposing likelihood support. Across all2522 windows,1350 positive losses total2672.425732 and1172 negative losses total−2262.759292; the ten largest positive windows contribute only2.104% of positive loss. A few isolated outliers therefore do not account for the full ranking.

Full-versus-CV bin signs agree in11/12 observed bins, but bin4 reverses from−348.990 in the accepted paired CV prediction to+163.389 at the full-training states. These comparisons have different fitted timing, clock/calibration and q parameters, and the full endpoints also released geography. They do not isolate temporal correlation, effective sample size, or the effect of one chosen block. Odd prediction bins involve the rejected near fold0 state and remain explicitly diagnostic, not completed accepted CV evidence. No block was dropped or downweighted.

The strong temporal/band structure motivates examining preservation of coupled training-derived nuisance states before another scalar weighting change. Saved fold scores also suggest a lower full-training basin at one accepted CV state; that arithmetic requires its separate direct full-target replay and stationarity audit. This block audit alone establishes neither global likelihood preference nor a valid alternative stationary solution.

Output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-detectability-blocks-059-v1`. Terminal SHA256 `cea8d6e56897f851b21ead289198a6108adfd807054dea8a5bf62e94b1d19e32`; scientific seal `537649b077aafacd41407b2ed6325a1f6d2afd87beaedfdb93fd58a062f0bfff`. One worker, internal120/TERM135/KILL140 seconds including source checks and preparation; exactly two objective calls and zero optimizer calls.
