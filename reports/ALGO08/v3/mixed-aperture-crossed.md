# Visit times and residual ranks in the mixed stereo schedule

On physical DS30-0016, dropping three visits per eight increased horizontal error **2.074 / 2.072 km** with both ranks eligible and **3.587 / 3.592 km** with nonanchor primaries. Keeping all times with nonanchor primaries passed the position gate on both containing offers. Its projected CPU exceeded both targets even with free short calls, so no new displaced replay or raw run qualified.

## Matched saved fit

Every cell starts from the same authenticated stereo pre-continuation ledger and changes only the eligible visits and native ranks. Anchors at zero modulo eight choose the largest verified margin. Both-ranks cells use that choice everywhere they retain a visit. In primary cells the remaining retained visits admit only an original 20 ms rank-zero factor. Both receivers share the schedule, keep their independent observations, and retain empty rows and counters. Every cell uses the same six-point quadratic graph, full-catalogue signed route, causal archive, geographic offer, both calibration arms and complete evidence checks. The earlier reduced-primary result in each case was reused after verifying full packet and solver identity. The other cells ran before verifying that the southern rank-policy pairs had equal native digests.

| Offer | Visit times | Nonanchor eligibility | Input factors / selected rank one | Owners, both arms | Horizontal km, c=0 / fitted | RF RMS Hz, c=0 / fitted |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| DS30-0016 | All | Both | 552 / 14 | 144 | 2.982 / 2.977 | 121.42 / 121.37 |
| DS30-0016 | Reduced | Both | 350 / 8 | 95 | 5.056 / 5.048 | 115.38 / 115.30 |
| DS30-0016 | All | Primary | 552 / 0 | 163 | 1.857 / 1.836 | 138.00 / 137.84 |
| DS30-0016 | Reduced | Primary | 350 / 0 | 95 | 5.445 / 5.427 | 115.25 / 114.97 |
| South containing | All | Both | 531 / 0 | 509 | 0.518 / 0.426 | 7.29 / 6.83 |
| South containing | Reduced | Both | 334 / 0 | 332 | 0.588 / 0.441 | 6.88 / 6.41 |
| South containing | All | Primary | 531 / 0 | 509 | 0.518 / 0.426 | 7.29 / 6.83 |
| South containing | Reduced | Primary | 334 / 0 | 332 | 0.588 / 0.441 | 6.88 / 6.41 |

On DS30-0016 both time reductions removed 202 input factors and 182 prepared graph points. All four cells kept five curved tracks. With full coverage, using nonanchor primaries improved position by 1.125 / 1.141 km and increased RF residuals by 16.58 / 16.47 Hz on the resulting owner sets. The gain came with 163 instead of 144 published owners, 142 shared, and zero changes of NORAD or role among shared IDs. With reduced coverage, using only nonanchor primaries instead increased error by 0.389 / 0.379 km. The prior complete result using the production continuation and its original graph was 1.644 / 1.661 km. The all-times primary result is 214 / 174 m worse than that control, passing the prespecified 250 m dual-arm threshold.

For the southern packet, no verified residual candidate had the winning margin. The two rank choices at each time support produced byte-identical native packet digests, science digests, states, reported arms and owner rows. Dropping visits removed 197 input factors and reduced published owners from 509 to 332. The time supports shared 322 owner IDs in each arm, with 27 role changes and unchanged NORADs. Holding extra visit times improved position by 70 / 15 m, while RF residuals increased by 0.41 / 0.42 Hz. All eight containing fits completed without fallback. Frequency residuals are in-sample on each resulting support.

## Charged short-call projection

The projection preserves recorded acquisition outside native calls, charges the observed stock calls for every full anchor and charges saved selector and complete solver CPU. It prices each 12 ms primary lane using the observed dense or weak microbenchmark rate of 1.073 or 1.735 ms. The two projections apply the rates uniformly to scheduled lanes. Their waveform observations are still full-aperture proxies.

| Offer | Primary schedule | Paid short lanes | Complete solve CPU s | Free-short floor CPU s | Dense / weak projection CPU s | Half matched / prior CPU s |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| DS30-0016 | All times | 1,240 | 3.140 | 5.717 | 7.047 / 7.868 | 5.197 / 4.613 |
| DS30-0016 | Reduced | 708 | 2.826 | 5.403 | 6.163 / 6.631 | 5.197 / 4.613 |
| South containing | All times | 2,096 | 4.127 | 8.005 | 10.255 / 11.642 | 6.756 / 6.188 |
| South containing | Reduced | 1,200 | 3.889 | 7.767 | 9.055 / 9.849 | 6.756 / 6.188 |

For full coverage the unchanged acquisition plus saved solve alone costs 5.102 s physical and 7.191 s south. Even if full and short native calls and selector work were free, both cases exceed the prior half target, and the southern case exceeds the matched half target. Actual authenticated raw clocks, short-waveform localization, and a displaced full-coverage result remain unmeasured. The sealed previous reduced-primary replay for the same displaced southern packet ended in a false fix at 71.286 / 75.450 km after a charged 9.480 s solve including fallback, with no completed exterior veto.

The [preregistered rules](mixed-aperture-crossed-protocol.md), [summary and hashes](measurements/mixed-aperture-crossed.json), [full solver receipts](measurements/mixed-aperture-crossed.json.gz), and [previous displaced result](measurements/mixed-aperture-availability.json) preserve the two comparisons.
