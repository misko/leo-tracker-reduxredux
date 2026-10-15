# DS22-B071 conditional/q CV: modest single-fold gains, both q pairs incomplete

Exactly eight declared fixed-position profiles completed and sealed. Six pass strict stationarity: all four conditional controls and the two fold0 detectability fits. BOTH fold1 q fits are rejected despite solver success. Consequently neither q geography has an accepted two-fold aggregate. This is weaker/mixed evidence than the earlier DS21-B059 experiment; it does not validate a DS22 localization improvement or justify retrying a rejected profile.

The original training-selected all/high XY are[92.4307536921,189.6997704041]/[−90.0605400151,−80.2093942814]km in the same original59-satellite frame, with their own original25km disks. Every profile starts with the SAME original full non-geographic/calibration/clock state and zero q. Original model/priors/fitted c and q budget1.6/box±2/N(0,1)/scale.5/sigma125Hz remain unchanged. There is no reference-based geometry selection and no geography movement in these fixed profiles.

Frozen v1 source `906157903` failed after TWO source-oracle objectives, zero fits: an original physical timing shift20.000000000000007s was feasible, but the original fitter's1ns inward margin changed a chart coordinate1.094285551e-9, exceeding the original1e-9 chart-identity gate. The entire failure is retained. New v2 `077c50cb6`, five owned tests/Ruff before freeze, explicitly records raw/canonical seeds and allows only the ORIGINAL initializer: first seven physical coordinates and nuisance/q exactly unchanged, max absolute satellite timing change1.000006936e-9s≤1.1e-9, second initializer change exactly0. Canonical-minus-raw legacy J is9.41509e-8, reported rather than called byte-identical.

V2 qualification completed487 objectives/zero fits in45.695s, including original legacy replay, all new fold/geography zero-q nesting and all58 nonzero-q finite differences (maximum6.74231e-8), full/fold prior-corrected physical+nuisance gradient closure and posterior/residual/q transport. The unchanged random whole20-second-block helper uses seed20261014 without redraw. Fold0 has1527 windows in blocks1/2/3/4/11/14, fold1 has1441 in6/7/8/9/10/12; complete shuffled IDs/map/hash persist. These are ORIGINAL training windows only.

| Fit fold/geography/arm | Strict accepted | Fit J | Predictive conditional-CFO NLL | Predictive event NLL |
|---|---|---:|---:|---:|
|0/all/conditional |true |19761.114774 |18774.765307 |20549.441420 |
|0/all/q |true |19294.132163 |18614.456488 |20396.123266 |
|0/high/conditional |true |19772.541650 |18971.863681 |20746.539794 |
|0/high/q |true |18323.308630 |18919.233887 |20700.120036 |
|1/all/conditional |true |16875.499644 |20288.752104 |22166.137173 |
|1/all/q |**false** |14999.775899 |20527.824498 diagnostic |22420.579952 diagnostic |
|1/high/conditional |true |17924.689356 |20280.304263 |22160.894426 |
|1/high/q |**false** |16663.553324 |20288.201132 diagnostic |22179.702434 diagnostic |

Scoring is on the OPPOSITE fold after all eight outcomes seal; both listed predictive scores exclude priors. The q-minus-conditional accepted fold0 changes are all−160.308819 and high−52.629794. The all geography gains167.802458 on low but loses7.493639 on high; the high geography loses7.503793 on low but gains60.133587 on high. Thus these gains are not uniformly supported by both bands. At fold0 q, the original all geography predicts304.777399 NLL better than the high geography. The two accepted conditional fold aggregates are all39063.517410 versus high39252.167945, also favoring all by188.650534. No q two-fold total is eligible.

Fold1 q all/high KKT.001167694/.002848607 exceed unchanged.001. They stop at3.440/3.557s,590/506 evaluations, both solver success; the20s cap does not explain rejection. Rejected diagnostics worsen predictive NLL239.072395/7.896868 versus their conditional controls. No threshold change, endpoint polish, replacement call or budget reallocation follows. All successful/rejected parameter vectors and conditional/event/per-band/RX counts, masses and priors remain saved.

Each fit retains20s/600. Eight separate workers ran at most two concurrently, each whole120/135/140 including source checks/preparation/audit. Whole workers take39.537–49.263s; preparation/source authority checks dominate the2–4s fitting scale. Evaluation took44.884s, eight objectives/zero fits. These are extra calls after the original18 B fits and discovery/initialization, not an equal end-to-end method. All source discovery/bank/frame/nodes/geographies/common initialization were full-training-derived; this is conditional development CV with shared leakage, not untouched validation. Original held/locked measurements and configured reference positions were never read.

The separately approved next experiment freezes ALL SIX accepted complete CV states, independently replays each on its own full target/domain, and gives each exactly one FREE continuation. Both failed q states remain excluded. This tests an optimization lead without promoting the incomplete CV evidence. DS22's configured reference remains unconfirmed; no target-accuracy claim is permitted.

Output `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-b071-randomized-cv-v2`. Qualification SHA256 `ded4e1ee11e50b4987cac76523b146ee94196f765e5dccab69ee06939b2e6f52`; scientific seal `91f4de43418f5d7ed45ca32a65fbc197a443b4d7a6cb4a277faab4ce84520831`; postseal cross-fold evaluation `65ce52418a7ff8f56691bca587c89263d11f75fef72e1b7923331a4e51b45fbf`. Failed v1 remains alongside in `ds22-b071-randomized-cv-v1`.
