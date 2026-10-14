# Current B035/B029: coupled calibration and orbit/association modes

The matched diagnostic does not isolate a missing clock term. Swapping only the
half correction or only the half orbit/timing prediction worsens likelihood on
every band of both cases. Their paired changes recover each own-half likelihood,
showing coupled fitted modes. The frozen operation completed in 24.264 seconds
including preparation: six full objectives, six additional orbit evaluations,
22 additional likelihood evaluations and zero optimizers. No held or reference
data entered it.

These are the latest consistently versioned coverage cached-v2 states, rather
than the older original shared-six039/023 results. The independently sealed
configured-reference errors provide context only:

| Case | Full B, km | Low B, km | High B, km |
|---|---:|---:|---:|
|035|96.957197|176.993018|181.039206|
|029|63.286893|84.384028|57.508901|

035 is an absolute failure shared with the other models, although full B beats
both halves there. On029 full B is worse than high B. Half-view pipelines inherit
the shared discovery bank/proposals and are not independent end-to-end systems.

All four columns below use exactly the same observations and candidate bank
within each row. Lower training NLL is better. Sample counts make the summed
scores interpretable; comparisons across different rows/banks are not selectors.

| Case/band | Windows | All orbit + all correction | All orbit + half correction | Half orbit + all correction | Half orbit + half correction |
|---|---:|---:|---:|---:|---:|
|035 low|1714|22602.862|25073.846|24717.405|22221.671|
|035 high|1193|15380.176|16954.031|17006.670|15765.774|
|029 low|1500|19590.523|21026.902|21087.533|18486.560|
|029 high|1172|14086.476|16048.799|16188.876|14123.465|

The full fit's high-band likelihood beats its own high-only fit in both cases,
whereas the low-only fit improves its low likelihood. The two full baseline band
scores sum to the exact full NLL. These hybrid prediction arrays are not feasible
new calibration states, calibrated-model evidence or selection candidates.
The orbit block combines geography and common/relative satellite timing; it
cannot isolate a geographic change. Original prior components were separately
replayed and closed. They are not included in this hybrid table.

Same-window conditional satellite-plus-clutter assignments differ substantially:

| Case/band | Mean TV, own full vs half | MAP changes | Both ≥.9 confidence, conflicting | Total correction difference RMS, Hz |
|---|---:|---:|---:|---:|
|035 low|.747898|1310/1714|1036|1467.670|
|035 high|.790852|966/1193|737|2161.506|
|029 low|.425429|631/1500|427|2834.715|
|029 high|.231322|249/1172|137|836.817|

Aggregated MAP changes are 78.294% on035 and32.934% on029. These are conditional
model assignments, not identity truth. Full/half frozen correction functions
were evaluated at identical physical timestamps/RFs/receiver IDs; no coefficient
copying or fitted-state transport occurred. Linear, clock and group component
differences are gauge-dependent across centering frames. Their total correction
difference is the physical comparison. Clock component RMS differences alone
(035670/429 Hz;029285/215 Hz) therefore cannot diagnose clock hardware or justify
replacing the clock model.

At the original full fit, added receiver-band drift score derivatives are
035[-4.280564,-48.828748] and029[-10.225780,-2.168193] objective per Hz/s. The
existing zero-centered drift prior derivative would be zero at that point.
These nonzero derivatives establish local training descent directions only;
they do not establish better localization. No drift fit is justified by these
directions alone.

The parallel bank/proposal inventory found major before→after replacement on
both cases. That independent evidence motivates preserving the union of original
and coverage banks and all twelve training-derived starts before introducing
more clock flexibility. This diagnostic neither proves candidate omission nor
rules out other global modes; it shows why a calibration-only swap is insufficient.

Source/protocol commit `2b2894a04`; six component/runner tests and Ruff passed,
including likelihood/prior/frame closure, added-drift finite differences, explicit
rejection of non-B likelihoods, altered bank and duplicate launch. Namespace
`local/model-b-current-fusion-v1` froze1004 bindings before preparation. Terminal
SHA256 `dea551289d49be1fc275080d7f2573f231b2c96a76cdd5f15b53af4832e23b4d`;
seal SHA256 `eefc6c396d4257171329014162fedd8ebd189e6a860bdf01775bd5c81bb347bd`.
The original sources/results and baseline histogram rows remain unchanged.
