# Fresh matched regional result: sparse gains are small and weight-sensitive

All six approved cold regional jobs completed under their240scaps, with two
workers, original iteration budgets and both matched c arms. Runtime was
101.6–112.9sper job. All twelve endpoints replay exactly in the independent
audit; paired c arms share likelihood observations, candidates and aliases.
Sealed inputs remain unchanged. Eighteen inference-process read receipts show
no denied inference read or GPS/oracle data access. All terminal outputs and
the inference audit were written before the reporting-only reference was used.

| RF-selected development case | Variant | c=0error(m) | fitted-cerror(m) |
|---|---|---:|---:|
| DS24-0011 | Fresh baseline | 1727.734 | 1567.031 |
| DS24-0011 | Additions, existing proxy | 1727.850 | 1567.353 |
| DS24-0011 | Additions, one-bin floor | 1728.103 | 1567.007 |
| DS24-0097 | Fresh baseline | 888.345 | 833.121 |
| DS24-0097 | Additions, existing proxy | 847.173 | 790.166 |
| DS24-0097 | Additions, one-bin floor | 883.403 | 826.023 |

DS24-0011changes by less than0.4m in either c arm/weighting variant, with no
meaningful gain. DS24-0097improves41.17m(c=0) /42.96m(fitted-c) with the old
proxy, or4.94m/7.10mwith the conservative full-bin scale. Its proxy relative
improvement is4.63%/5.16%; floor improvement is0.56%/0.85%. This is a small
development effect sensitive to new-point weighting, not evidence of the
proposed10%held-validation median gain or a new location result.

The regional pipeline admits two newly curved likelihood owners in0011and
three in0097, fewer than the four graph-curved proposals in each case. No new
predictive owners enter either fit. Total likelihood change is+3/+3for proxy
and+2/+3for floor across0011/0097; graph repacking can also change an incumbent's
likelihood role while its original measurement row remains intact. Original
frequencies and margins were never replaced, and no satellite identity was
forced onto the additions.

The existing-output attribution audit resolves0097more specifically: all3,243
baseline likelihood IDs are retained with exactly the same candidate labels,
roles and aliases; no incumbent likelihood owner is gained or lost. Proxy and
floor also have identical likelihood IDs/labels/aliases and exactly identical
incumbent effective noise scales. Thus the35.86m fitted-c difference between
proxy and floor is new-owner weighting sensitivity, not an incumbent association
change. Relative to the baseline, however, relearning the proxy changes4,226old
observation scales by−0.130to+0.888Hz. The existing artifacts cannot fully split
the residual7.10m floor gain between those small global reweightings and the
three new owners; no extra counterfactual sweep was run.

The three0097likelihood additions are CH6-F40/nativeRX1, CH5-F80/nativeRX0and
CH5-F40/nativeRX1. Their residual FFT innovations are−7102.27,−4882.81and
−6658.38Hz(−16,−11and−15bins), respectively; all use a one-donor mode. These
three are not zero-bin copies of an already-accurate prediction. Their proxy
scales are98.75,94.25and103.14Hzversus the443.89Hzsensitivity floor. Exact
native IDs/counters, candidate assignments and aliases are in
`position_attribution.json`; they were determined by fresh full-catalogue
inference, not prescribed satellite identities.

Curved frequency RMS increases slightly: proxy+0.165/+0.166Hzin0011and
+0.122/+0.127Hzin0097(c=0/fitted-c); floor+0.064/+0.059Hzand+0.152/+0.151Hz,
respectively. Position and frequency fit therefore have separate outcomes.
Changing observation sets also changes objective normalization; lower total
objective alone cannot establish better localization.

The one-bin443.892Hzfloor changes only new owners' effective noise scales
relative to the proxy variant. All incumbent effective scales remain exactly
the same between those two addition variants. The existing per-ID selector is
labeled an explicit research override: its+1activation sentinel is not a
measured BIC gain. Neither that floor nor the old margin/residual proxy is
claimed calibrated. Shared donor-dependent FFT origins remain a dependence
limit; eight of thirty sparse new outputs have zero residual bin and numerically
equal their earlier prediction.

The actual bottleneck is now narrower than detection alone: only14of30new
native pilots enter a raw curved graph across the twelve development cases,
and only a handful enter these two causal regional likelihoods. The root's
separately frozen24scoherent application tests whether they persist as useful
Doppler sequences. It must keep separate inputs/receipts from this completed
sparse-position comparison. No held-validation target outcomes were opened by
this regional sensitivity and no full-dataset promotion is authorized.

Exact results: `position_evaluation.json`; pre-GPSaudit:
`position_inference_audit.json`; terminal seal: `position_terminal_seal.json`;
active source/input protocol: `position_protocol_v2.json`. The initial protocol
and failed read-only library-metadata preflight remain preserved. The narrowly
amended guard passed before any inference job; no numerical job was retried.
