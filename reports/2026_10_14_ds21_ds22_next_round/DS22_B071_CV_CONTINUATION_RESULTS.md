# DS22-B071 accepted-CV continuation: q still selects a distant mode

The full-training q selector remains distant: **321.775759km** from the configured, UNCONFIRMED reference. An accepted high-origin q state is.999762km away but loses training objective2058.966252. It cannot be selected by known distance. The conditional selector retains the original324.778372km state. Thus the DS21-B059 single-case recovery does not transfer to071 in this control. These are configured-reference distances, not verified position accuracy, and no prototype is promoted.

Exactly ALL SIX accepted randomized CV endpoints were declared before fitting: four conditional and two fold0 q states. Both rejected fold1 q profiles remain excluded and their two-fold predictive comparisons remain incomplete. Every start carries its COMPLETE fitted physical/nuisance/q state, own original25km disk, unchanged59-bank/full frame/nodes/priors/fitted c and own observation arm. No non-geographic reset, q reset, new geographic anchor, reference choice or failed-profile retry occurs.

Source/protocol `a5d4398a5` passed five owned tests and Ruff before freeze. Full-target qualification completed20 objectives/zero fits in29.156s: source/opposite/full replay for each endpoint, exact prior-corrected NLL/physical+nuisance gradient additivity and common-row posterior/residual/q transport, plus two original full baselines. Original conditional baseline J36581.420508/NLL35641.133633/KKT.000362768 is eligible. Its zero-q counterpart has the same J/NLL but q-tail KKT127.781994 and is NOT an eligible stationary incumbent. This distinction is enforced, not assumed.

All six CV states are nonstationary on full training (KKT794–4555), despite strict source-fold acceptance. Their full replay objectives are38535.880081/37908.588651 for fold0 all conditional/q,38744.405331/37242.542517 for fold0 high conditional/q,37164.251748 for fold1 all conditional and38204.993619 for fold1 high conditional. Raw complete endpoints are passed unchanged to the original fitter; its existing stable nanosecond timing-margin convention is separately recorded, without nuisance clipping or physical-domain relaxation.

| Full FREE source | Accepted | Full J | Full NLL | FREE KKT | Configured distance km |
|---|---|---:|---:|---:|---:|
| original conditional **selected** |true |36581.420508 |35641.133633 |.000362768 |324.778372 |
| fold0 all conditional |false |36345.889974 |35551.947026 |.001377315 |323.489394 |
| fold0 all q **selected q** |true |34794.647431 |33952.216317 |.000864781 |321.775759 |
| fold0 high conditional |true |37475.664784 |36893.878673 |.000201964 |9.511383 |
| fold0 high q |true |36853.613684 |36500.576289 |.000122398 |.999762 |
| fold1 all conditional |true |36662.033858 |35982.029568 |.000331632 |329.783154 |
| fold1 high conditional |true |37910.078477 |37347.848575 |.000181066 |3.456480 |

The accepted q high-origin state loses **2548.359972 NLL**, while its prior is489.393720 LOWER (353.037395 versus842.431115). Priors therefore do not primarily explain this selected-mode discrepancy. A nearby accepted state exists in the original declared disk; this specific test does not fail merely for missing a nearby initializer. It also does not exhaust better states or establish an inevitable likelihood preference. Earlier cross-fold results favored the original all geography on the one fully accepted q fold and did not validate q on both folds; position alone cannot overturn those limitations.

The rejected conditional continuation has J235.530534 below the retained original, but strict KKT.001377315 rejects it despite solver success at5.591s/509 evaluations. This is another numerical/optimization lead, not an accepted improvement or a reason to loosen the gate. There was no retry/polish. Accepted q all-origin improves below the original feasible zero-q bound36581.420508, so its reported selected score is not worse than that known bound. High-origin and all-origin disks are distinct; the far original is not a feasible point in the high disk.

Exactly six new20s/600 FREE calls ran, up to four single-thread workers. Five accepted, one rejected; fit times3.906–6.081s, whole workers32.545–35.535s within120/135/140 including source guards/preparation/audits. Source CV eligibility produces unequal realized counts (four conditional/two q), not an equal end-to-end arm budget. Original18 B calls, eight CV calls and all upstream discovery/preparation remain separate cost. No original held/locked measurements were read.

All six outcomes and own-arm training selectors sealed before configured-reference comparison. The small tested postseal evaluator `255c07281` uses the existing exact-hash reference parser, makes zero probability objectives/fits and explicitly sets target_accuracy_claim_permitted=false. Original baseline/histogram rows remain unchanged. Next diagnosis should compare observed within-training predictive band losses and zero-posterior hard-visibility normalization leverage; no new q starts, prior/bound tuning or truth-weighted observations follow from this result.

Output `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-b071-cv-continuation-v1`. Qualification SHA256 `cb4a6c033f79e99e7b8ad07696b45b470782625b3628b4dcd4b763026c3769b3`; all-six scientific seal `b0644b98966256fb49724825ae80b9c41b28392e723b938dae3b3cc8cb80c40a`. Separate comparison: `ds22-b071-cv-continuation-comparison-v1/report.json` under the same bulk root. Reference source SHA256 `6de071077d8c2fe11a991b665c50edaf728ef9ffd320dca36cfedc44ee874bf9`, status configured-unconfirmed.
