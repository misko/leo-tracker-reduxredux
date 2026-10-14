# C053/C081: different failure mechanisms in the completed cohort

The unchanged original six-start coverage results select 253.925 km on DS21-053
and 253.243 km on DS21-081. A new matched endpoint-initialization experiment
reduces C081's selected error to **15.115 km**, with strict convergence intact.
It still loses to that case's 11.070 km low-band and 7.866 km high-band fits;
the requested localization target is not achieved.

## Zero-fit audit

The sealed audit includes all six full endpoints, accepted or rejected, and both
own-half winners for each case. It reproduces saved objectives/NLLs, decomposes
native full-state NLL by band, and checks original physical domains. No reference,
held observations, or fitting is used. Sixteen objective calls and twelve explicit
orbit predictions completed in 17.516 seconds under 120/135/140-second limits.

C053: all six full fits are stationary. Selected start 5 has objective 24063.647
and NLL 23656.812; it beats every other full endpoint in **both** band likelihoods.
Its disk radius is 20.592 km, so the selected solution is not pinned to a disk edge.
Both half winners are also distant: 250.376/255.275 km. This case is a shared
discovery/assignment failure rather than an all-band-only degradation. The old
before C result was 9.592 km, but its bank and proposal population differ; scores
cannot be compared directly across those banks.

C081: original full start 0 has objective 26250.271183, substantially better than
the accepted winner start 2 at 28251.044115. Start 0 is rejected: its original
20.057-second/447-evaluation run ends with KKT 0.514074. Both endpoints are inside
their original 25 km disks, at radii 3.371 and 5.217 km. Their band NLLs are:

| Original endpoint | CH1–4 NLL | CH5–8 NLL | Acceptance |
|---|---:|---:|---|
| Start 0 | 15555.832 | 10336.042 | Rejected |
| Selected start 2 | 16490.347 | 11348.470 | Accepted |

Both bands favor the rejected endpoint. Another full start (4) converges to an
all-clutter solution, with zero satellite signal mass and objective 33206.783;
stationarity alone does not establish a useful solution. The own-half winners
both originate at proposal 4 but occupy different calibrated states.

## Matched endpoint-initialization experiment

The trigger was fixed from training evidence: among the twelve audited endpoints,
only rejected C081 start 0 scores below its accepted case winner. Two new fits use
that endpoint and the accepted incumbent as initial states, each in its own
unchanged original disk with the original model, bank, priors, fitted c,
20-second/600-iteration allowance, and KKT threshold. The original accepted
incumbent remains eligible in both arms. Neither position error nor reference
coordinates choose the trigger, initializer, disk or selected result.

This is an additional, separately frozen two-fit experiment, not a replacement
of a failed receipt or an equal-total-budget claim against the original six fits.
The original failed attempt is preserved. Both endpoint initializers pass original
domain checks without any adjustment. Both new fits are accepted:

| Arm | Objective | KKT | Evaluations | Fit seconds | Selected error |
|---|---:|---:|---:|---:|---:|
| Rejected-endpoint initializer | 26250.271159 | 0.0000171 | 284 | 8.723 | 15.115 km |
| Accepted-incumbent initializer | 28251.044115 | 0.0003942 | 18 | 0.582 | 253.243 km |

The paired run completed in 17.866 seconds. Its objective barely changed from the
original rejected endpoint (−0.000024), but the convergence audit now passes.
This isolates acceptance attrition as the cause of the catastrophic original
selection on C081. It does not explain the residual 15 km error or justify
relaxing acceptance. The result stays separate from baseline histogram013.

## Evidence

- Audit source `8aec225e8`, actual native replay/domain/nonmutation test and Ruff pass.
- Endpoint experiment source `d500184c1`; matched-call/domain/original-eligibility/
  no-retry test passes. The frozen driver retains one nonfunctional Ruff E501
  line-length finding; it was not altered after freezing.
- Postseal evaluator `6ea118253`; premature-reference guard test and Ruff pass.
- Audit namespace: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-later-failure-audit-v1`.
- Audit result SHA256 `ca939206e2cc72f451c988164204b7de4b93957542ec2eb8041e194caa7816b0`.
- Experiment namespace: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-c-endpoint-start-081-v1`.
- Terminal SHA256 `6ca7aba008b2ad3245e6f282130b9ac48172dbe5d8f55cd76f33da9b18fadaa8`.
- Seal SHA256 `6fef968bacaf43131ccb12cf88eeb54370e9e434dcb917b6e976be048eac6402`.

These are repeatedly inspected development cases. A general endpoint-preservation
policy needs a declared broader matched-budget evaluation before promotion.
