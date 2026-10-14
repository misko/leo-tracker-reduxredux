# DS21-039 relative-phase control: no accepted combined-band solution

The prespecified twelve-call fitted-c control completed in 127.881 seconds.
Ten fits passed stationarity. Both CH1–8 relative-phase starts exhausted their
20-second fit budgets without stationarity, so the alternative has no accepted
combined-band estimate. This is not evidence that the physical convention is
wrong, and it is not an accuracy improvement.

All fits and training selections were sealed before held prediction and
configured-reference evaluation. The immutable freeze binds 332 source files
and preserves the original seven-call refinement authority, candidate bank,
partitions, priors, two physical starts per view, and 600-iteration limits.

| View | Receive-epoch control error, km | Relative-phase error, km | Control held NLL | Phase held NLL |
|---|---:|---:|---:|---:|
| CH1–8 | 4.072515 | Unavailable | 7305.961858 | Unavailable |
| CH1–4 | 3.758515 | 2.894677 | 4319.369154 | 4322.787734 |
| CH5–8 | 4.163056 | 2.919883 | 2984.144036 | 2984.838371 |

The half-band position errors decrease relative to this matched two-start
control, while both held likelihoods worsen slightly. No row reaches 0.5 km.
The control's CH5–8 result differs from the earlier 2.556792 km estimate because
the newly qualified second physical start wins the training objective here.
It is not permissible to choose between those estimates by reference error.

The two rejected combined-band phase fits have stationarity values 2092.255
and 6673.084. They used 164 and 167 objective evaluations in 20.168 and 20.114
seconds respectively, with solver success false. Their endpoints are retained
but are not accepted positions. Before another fitting experiment, check the
actual saved-state derivatives and objective evaluation cost to distinguish
optimization-budget limits from a modeling defect. Do not silently retry these
fits or relax their stationarity criterion.

Local evidence: `reports/2026_10_13_ds21_039_root_cause/local/relative-phase-v1`.
Freeze SHA-256: `3be44fca015af820c33b0109e8ab375620530eac3c77865aab0657458f2967ec`.
Twelve-fit terminal SHA-256: `9ef68bb4ef433cf6274ce9204212180106b616b43a9ea99c48d9a12db15a71d4`.
Evaluation SHA-256: `a8dd5680737e0c93da7b480a913938578392ba96ed23b6fe74b8e761d9c9862c`.
The reference is configured, not independently surveyed. The phase convention
is a mechanism sensitivity test, not a physically attested timing correction.
