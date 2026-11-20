# Soft orbit identity from native factors

The soft receiver published all ten roof recordings and withheld all three wrong offers. The exact joint receiver published nine roofs and withheld the same three wrong offers. On the seven shared reserve fixes, the soft receiver increased paired median geographic error by 628 m at c=0 and 735 m with fitted c. Qualification stopped at the 13-query challenge under the locked geographic criterion.

## Receiver and evidence

The receiver fits one shared training-only location and radio state per arm. It keeps a fixed anonymous causal shortlist for each track, estimates two receiver-wide RF-fractional linear rates and four mixer offsets, and uses log-sum-exp over orbit and CFO-wrap alternatives. The optional coefficient adds one dimension. Altogether the shared fit uses eight or nine continuous coordinates, three CFO aliases per shortlisted orbit, and one bounded 64-iteration solve per arm. An explicit contamination plateau downweights objects that lack plausible explanations. Position is taken directly from the shared training fit at publication.

Bayesian phase marginalization is approximated by bounded per-alternative phase profiling with the Gaussian volume term. The model uses tile-center orbit and phase derivatives and treats tracks conditionally independently, including multiple tracks that may belong to one satellite. Satellite-level discrepancies therefore enter through separate track phases. The contamination weight and plateau are fixed robust scores. Their posterior mass is interpreted as a gate statistic. The observed-mixture curvature includes the alternative-gradient covariance, along with the profile curvature and prior.

Both arms use identical factors, anonymous tracks, temporal split, candidate objects, alias alternatives and optimizer budgets. Held tracks contribute no shared-state update. They are scored with the same local orbit/alias branch mixture at the frozen training state. The old exact joint receiver ran separately on the same native Graph and performed its normal pooled fit. On twelve inputs with prior independent replays it reproduced the same input, native factor, catalogue, Graph and peak-count receipts, decisions and arm coordinates. The close omitted offer had the two fresh measured fits. The report includes the four authentic archived original v5 execution roles.

## Geography and held evidence

The two designated diagnostics were DS26-0036 and DS29-0082. The eight reserved by opaque ID were DS26-0301, DS26-0082, DS26-0006, DS26-0114, DS26-0150, DS26-0215, DS26-0195 and DS26-0044. The three omitted offers placed the site 30.48 km, 22.52 km and 1.24 km beyond the tile edge.

| Reserve method | Published of 8 | Median geographic error c=0 / fitted c (km) |
| --- | ---: | ---: |
| Soft orbit identity | 8 / 8 | 2.697 / 2.524 |
| Exact native joint | 7 / 7 | 1.882 / 1.584 |
| Original no repair | 8 / 8 | 0.667 / 0.683 |
| Original selective gap | 8 / 8 | 0.667 / 0.683 |
| Original one omitted track | 8 / 8 | 0.637 / 0.656 |
| Original omitted tracks | 8 / 8 | 0.637 / 0.656 |

All three omitted offers passed the soft held gate in both arms. Mean inlier mass on those wrong tiles ranged from 0.944 to approximately 1.0. The close offer showed 105 Hz held RF RMS at c=0. The interior-position gate was the recorded reason for all three wrong-offer rejections. Actual reserve error exceeded the nominal curvature radius on six of eight c=0 fixes and five of eight fitted-c fixes.

On the ten true roofs, fitting c changed paired geographic error by a median of +4.4 m and improved three fixes. It reduced the median RF error on training tracks by 0.44 Hz and increased held RF error by 1.77 Hz. The exact control models RF on its own fitted support, so its raw RMS is recorded separately. The geographic promotion uses paired published endpoints and conditioned publication counts.

## Runtime and artifacts

All 13 native comparisons completed in 24.4 s on four low-priority replay lanes under the 512 MiB address-space cap. The median reserve backend wall times were 1.597 s for soft and 1.644 s for exact. Both include anonymous track preparation, causal orbit shortlisting and inference. The median complete paired roof worker took 6.570 s and used 148.6 MiB peak resident memory. The reserve median function evaluations were 27.5 and 31.5 in the two arms.

The [per-recording scores](scores.csv) and [prediction lock](prediction-lock.json) retain both receiver outputs and the original reference outcomes. The [standard figure manifest](figures.json) covers the diagnostics, reserve and omitted offers, keeping hypothetical forced positions diagnostic. Rendered books for the [zero arm](charts/c0/modifications.pdf) and [fitted arm](charts/fitted_c/modifications.pdf) include all original v5 controls.
