# B059 sealed detectability coefficient audit

The zero-fit audit passed in12.274s with four original fold-training objective evaluations. All existing CV outcomes and acceptance flags remain unchanged. No original held/locked observations or reference coordinates were read. Source `0eb5a00f0` passed four owned tests and Ruff before freeze.

| Fixed geography | Cross-fold log-q correlation | Rank correlation | Top10 overlap | Budget-normalized TV | Jensen-Shannon |
|---|---:|---:|---:|---:|---:|
| incumbent |.779924 |.624903 |9/10 |.194555 |.034118 |
| donor |.602607 |.590939 |6/10 |.266712 |.078449 |

The incumbent has substantial repeated catalogue propensity structure. The donor is less stable, and its fold0 endpoint remains rejected; that agreement is descriptive. Neither result establishes correct satellite identities or a beam footprint. Full-training discovery/metadata leakage remains as disclosed in the [CV result](MODEL_B_OBSERVATION_CV_RESULTS.md).

The incumbent's top catalogue IDs are65094,65811,69045 in fold0 and56427,65094,69045 in fold1. The donor's top IDs are64845,66339,69230 and64845,63072,64104. These are fitted propensities under each geography, not authoritative emitter labels.

| Training unit | CV accepted | Active lower coefficient indices | Raw lower-face gradient range | q-tail scaled projected maximum |
|---|---|---|---:|---:|
| incumbent fold0 |true |30,50 |83.481–95.521 |2.691e-6 |
| incumbent fold1 |true |30,50 |67.739–88.565 |2.455e-6 |
| donor fold0 |false |28,40,51 |2.638–95.095 |4.659e-6 |
| donor fold1 |true |21,28,40,51 |8.535–52.898 |6.898e-7 |

All lower-face gradients point toward improvement outside the original frozen box, and correctly satisfy its constrained KKT. No upper face is active. Coefficient indices refer to the zero-sum basis and are not direct catalogue indices. Bounds±2, scale.5 and the original N(0,1) prior remain unchanged. The donor fold0 overall rejection at.001058490 is in an original physical/nuisance block, not the q tail; this does not authorize retrying or accepting that endpoint.

All four fold-training objective/NLL replays and timing/clock/group/q prior closures pass1e-7. Timing-relative priors are476.763/461.490 at incumbent and309.562/273.343 at donor; common-clock priors35.342/43.255 and12.026/13.723; q priors17.700/16.632 and22.898/27.013. Common timing priors are≤.0446 and group-offset priors≤.405. The likelihood improvement is therefore not reported as a prior reduction.

The evidence supports the proposed matched full-training normalized-control versus detectability profiles/releases, while retaining the possibility that a stable propensity also supports the wrong geographic mode. It does not warrant widening bounds, tuning shrinkage, choosing by known position, or promoting the incomplete donor CV comparison.

Output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-detectability-evidence-059-v1`. Terminal SHA256 `7c576161229f8da6ac40245c2739237970acd2a22e25d85dc24966398b73e2cc`; scientific seal `1b769a741021be2cec7977563486210e4b6350be41602c8f09e08a7057d10642`. The source-frozen audit used internal120/TERM135/KILL140 seconds, one numerical worker, four objective calls and zero optimizer calls, including preparation and source checks.
