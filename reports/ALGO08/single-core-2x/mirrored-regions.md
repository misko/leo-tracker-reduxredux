# Moving the offered square across a receiver

We moved each existing northern and southern near-edge square 200 m, placing the receiver **100 m outside the same face** instead of 100 m inside. The two offers for each site used identical waveform detections, capture-time orbit snapshots and width. The diagnostic had already been frozen at `0f6ad3a79`. It uses all 456 original observations at each site and can change satellite assignments at every probe. Positive gain would withhold a position. Receiver-specific gains are diagnostics. [Scoring rule and earlier controls](regional-reassignment.md)

| Public site and receiver position | Pooled exterior gain × 1,000 | Receiver 1 / 2 gains × 1,000 | Frozen decision | Correct region decision |
|---|---:|---:|---|---|
| North, 100 m inside | −0.545 | −0.638 / −0.451 | Keep | Yes |
| North, 100 m outside | −0.441 | −0.536 / −0.347 | Keep | No |
| South, 100 m inside | +0.047 | −0.067 / +0.160 | Withhold | No |
| South, 100 m outside | +0.187 | +0.074 / +0.300 | Withhold | Yes |

The score moved in the expected direction within each site when its offer moved outward. At the northern site, both receivers still favored keeping the fix in the omitted region. At the southern site, the pooled gain already favored withholding in the containing region. A single common threshold on this scalar cannot separate all four cases. In a separate saved-detection replay on the northern omitted offer, the stock solver returned positions **123 m from truth with fixed-zero calibration and 118 m with fitted calibration**. The diagnostic would have allowed those positions through despite the receiver being outside. On the valid southern offer, the published near-edge control had errors of 817 m and 1,101 m. [Pointwise evidence and northern solver output](measurements/region-mirrors.json.gz) · [Earlier near-edge controls](edge-trial.md)

Together the eight original offers and two additional omitted offers produced **3 correct keeps out of 4 containing offers** and **5 correct withholds out of 6 omitted offers** for the proposed diagnostic. All ten offers come from two public simulated sites. The sign rule remains experimental. Its false decisions in both directions are consequential for the fresh-location qualification gate.

To generate the two additional offers, run `edge_trial.py STATION_OFFER OUTPUT --outside` on this branch. The recording identifier selects the public test face in the evaluator only. The normal inference inputs are the saved detections, offer and capture-time archive. Run the same frozen `regional_reassignment_trial.py` invocation as in the original experiment with the new offer file. The two outside diagnostics and the northern position replay were serialized on one low-priority core on Gauss. [Offer generator](edge_trial.py) · [Diagnostic runner](regional_reassignment_trial.py)
