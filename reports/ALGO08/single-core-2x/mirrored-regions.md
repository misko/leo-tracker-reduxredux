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

## Fixed position membership in the mirrored offers

For each waveform and calibration arm, freeze the position from its separately published containing offer and test membership in both shifted squares. This gives the diagnostic an optimistic starting point. The scorer chose the anchor offer using its revealed containment label, and the original fit was constrained by that offer. The coordinates are independent of the two shifted offers. The use of a trusted anchor and containment labels is confined to this audit. The saved probe packets bind the same detections and causal snapshots across the original and mirrored offers. [Locked positions](../regional-release/predictions.json) · [Public scoring key](../regional-release/scoring-key.json) · [Original probes](measurements/regional-reassignment.json.gz) · [Mirrored probes](measurements/region-mirrors.json.gz)

Use the released local east and north coordinates in each square. The membership score is half the width minus the larger absolute coordinate. Keep when that score is at least zero. The west face is closest at the northern site and the east face is closest at the southern site, for both truth and both estimates. Positive across-face bias points into the square. The truth has +100 m and −100 m clearance in each pair, so the signed estimate error along the face normal must be at least −100 m and strictly less than +100 m to classify both offers correctly. Along-face error does not affect these four classifications because the other three faces remain farther away. [Released coordinate transform](../../../src/leo/analysis/localization_v3/region.py)

| Public site | Calibration | Horizontal error | Across-face bias | Clearance with truth 100 m inside | Clearance with truth 100 m outside | Membership decisions, inside / outside |
|---|---|---:|---:|---:|---:|---|
| North | Fixed zero | 744.6 m | −741.0 m | −641.0 m | −841.0 m | Withhold / withhold |
| North | Fitted | 711.2 m | −682.5 m | −582.5 m | −782.5 m | Withhold / withhold |
| South | Fixed zero | 825.9 m | +344.8 m | +444.8 m | +244.8 m | Keep / keep |
| South | Fitted | 1,108.7 m | +285.9 m | +385.9 m | +185.9 m | Keep / keep |

Each arm kept **1 of 2 valid fixes** and withheld **1 of 2 omissions**. The northern estimates need to move at least 641.0 m and 582.5 m inward, respectively, to reach the allowable across-face interval. The southern estimates need to move more than 244.8 m and 185.9 m outward, respectively. Fitting `c` improves the across-face error at both sites. In the south, its frequency RMS decreases from 6.503 to 6.392 Hz while horizontal error increases. [Scored original positions](../regional-release/blind-scores.csv)

A shared clearance threshold cannot repair the crossed errors. With fixed-zero calibration it would need to exceed +244.8 m to reject the southern omission and be at most −641.0 m to keep the northern valid offer. With fitted calibration the conflicting limits are +185.9 m and −582.5 m. Holding the anchor's RF RMS fixed also gives both offers at a site the same confidence value. These comparisons leave other region-independent estimators open. A future check can lock one upstream position per waveform and retain the same zero-clearance membership rule before scoring new offers.

The existing bound-gated far-exterior rule kept **both valid fixes** and missed **both omissions**. Both northern calls ran the veto and both southern calls bypassed it. For each of the four cases the receivers agree on a maximum 97.7 m beyond the face. Lowering the clearance bound alone would still miss the northern omission because both receiver gains there are negative. With the clearance relaxed, each receiver's northern omission gain also ranks below its southern valid-offer gain. A shared monotone gain threshold therefore cannot withhold the northern omission and keep the southern valid offer. All results here are from two public simulated waveforms. [Bound-gated decisions](measurements/regional-bound-guard.json) · [Per-receiver scores](measurements/regional-exterior-veto.json)

To generate the two additional offers, run `edge_trial.py STATION_OFFER OUTPUT --outside` on this branch. The recording identifier selects the public test face in the evaluator only. The normal inference inputs are the saved detections, offer and capture-time archive. Run the same frozen `regional_reassignment_trial.py` invocation as in the original experiment with the new offer file. The two outside diagnostics and the northern position replay were serialized on one low-priority core on Gauss. [Offer generator](edge_trial.py) · [Diagnostic runner](regional_reassignment_trial.py)
