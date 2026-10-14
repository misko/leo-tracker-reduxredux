# Union B:035 gains both bands;029 retains separated competing modes

The reference-free decomposition completed in3.039 seconds including preparation:
five full objectives,five additional orbit calls,ten restricted-band likelihoods,
zero optimizers. Exact original full-frame likelihood and prior closures passed.
The source24-call control and its training selectors remain unchanged.

035's all-twelve winner improves both bands over the union after-six winner:

|035 state|Low NLL(1714 windows)|High NLL(1193 windows)|Low signal/clutter mass|High signal/clutter mass|
|---|---:|---:|---:|---:|
|After-six winner,after5|22598.534|16064.510|820.34/893.66|495.77/697.23|
|All-twelve winner,before4|20830.748|14482.459|1277.49/436.51|901.14/291.86|
|Accepted runner,before5|21137.145|15133.764|1213.23/500.77|736.10/456.90|

The winning preserved-start basin is supported by both frequency bands under
this model. Its nearest accepted objective runner is1.613286 km away,with
objective gap977.700584=NLL957.701559+prior19.999025. Thus the tested035
selection change is not explained by a single band's likelihood or by prior
penalty alone. Conditional signal/clutter mass is model evidence,not satellite
identity truth or a separate accuracy validation.

029's two selectors coincide,so its accepted runner/best-before endpoint is also
included by the prespecified training-only rule:

|029 state|Low NLL(1500 windows)|High NLL(1172 windows)|Low signal/clutter mass|High signal/clutter mass|
|---|---:|---:|---:|---:|
|Both selectors,after2|19683.733|14432.196|716.85/783.15|766.85/405.15|
|Runner/best-before,before0|19464.090|14569.419|813.01/686.99|790.94/381.06|

These accepted endpoints are149.916800 km apart. The runner has82.420276 lower
total NLL,but220.148024 higher prior penalty,so its objective is137.727748
worse. Its low NLL improves219.643124 while high NLL worsens137.222848.
Relative timing contributes182.987026 of the prior gap; common-clock penalty
contributes36.311577,with the remaining0.849421 from common timing/group terms.
The likelihood tradeoff and separated physical modes make029 sensitive to prior
ranking within this tested set. They do not establish that the runner is more
accurate or justify relaxing priors. The earlier sealed accuracy comparison
already showed no029 improvement from adding the before starts.

All accepted endpoint gaps are retained in the artifact,including objective,NLL,
prior and great-circle separation from the training winner. Distances use the
same physical regional chart and fitted coordinates,independent of start center
or origin. No reference coordinates,held observations,new fit,calibration
transfer or alternate candidate set entered this diagnostic. Hybrid half models
were not used: each row is evaluated under the same fixed union/all-band model
and calibration frame for its case.

This strengthens the case for preserving useful starts on035 and investigating
ambiguity/model assumptions on029. It does not isolate a missing differential
clock term or establish a general clock/likelihood repair. The sub-kilometer and
matched full-versus-both-union-halves goals remain unachieved.

Source/protocol `90aab1e3d`; three owned tests/Ruff pass,covering training-only
role deduplication,prior/NLL gaps,reference-free geographic separation and the
unchanged B band scorer's actual objective count. Private namespace
`/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-union-band-audit-v1`.
Terminal SHA256
`0a30cd09d19c3732553ab7351ddc6bee2a06cb43647abdc101ef1b84eb9ba53c`;
seal SHA256 `3df6fe911278070d7032df15522bf3b33550bf4374a1f59768c5c64798e00887`.
