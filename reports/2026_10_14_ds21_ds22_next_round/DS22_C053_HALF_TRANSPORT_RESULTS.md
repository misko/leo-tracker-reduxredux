# DS22 C053: exact half transport and matched radius controls

The combined selector remains unchanged at 75.781770 km from the configured, unconfirmed station reference. Matched half-radius controls select LOW 26.442135 km and HIGH 30.915937 km. These are conditional shared-discovery comparisons, not independently discovered halves or verified position accuracy. No target is achieved.

| View | Original configured distance km | New selected distance km | Selection |
|---|---:|---:|---|
| All CH1–8 | 75.781770 | 75.781770 | Original incumbent retained |
| LOW CH1–4 | 27.083146 | 26.442135 | 50 km domain, radius31.414 km |
| HIGH CH5–8 | 30.491824 | 30.915937 | 50 km domain, radius31.733 km |

The source-frozen qualification preserved native correction functions to 1.17e-10 Hz, original receiver lifts and satellite timings, exact ephemerides and source observation identities. Masked objective/NLL closure was within2.92e-11; physical gradient pullback within1.95e-9. The full group's nuisance coordinates start at zero. Opposite-band correction is explicitly an extrapolated initialization, not independent half evidence. The qualification receipt field `full_group_gradient` contains the masked target gradient; it is not used as evidence of full-model stationarity.

Both original halves were on their own25 km boundary with outward derivatives −30.363 and−17.929, independently checked by finite differences. Matched25/50 controls all passed strict stationarity. LOW J23440.183→23096.287 and HIGH J21798.539→21701.955 improve training fit, but HIGH configured distance worsens. Local derivative evidence did not guarantee monotonic objective improvement: the qualification's fixed-nuisance1 km outward probes increased J in both halves.

The complete LOW-to-full fixed profile reveals a material search failure. Its feasible transported initializer has J50365.838662, whereas the chosen strict stationary trajectory point has J55704.855579 (KKT6.04e-5), a5339.016917 increase. The optimizer exhausted60 seconds; its strict trajectory selection must not be interpreted as an improved profile optimum. Its full-model outward derivative is positive4.673962, agreeing with finite differences, so the full50 km release was correctly skipped. The prescribed25 km release passed strict KKT3.25e-5 at J55685.607877, still worse than the original full incumbent J45613.177281. HIGH-to-full also exhausted60 seconds and failed KKT1973.690421; both releases were skipped. Thus this experiment does not rule out a better full solution from the feasible transported states.

All ten outcome slots sealed before reference access: seven actual fits, six strict outcomes, one nonstationary outcome, and three explicit skips. The six initial outcomes formed a barrier before any release. Original accepted incumbents remained eligible; training J alone selected outcomes. No source failure was retried or threshold relaxed.

| Unit | Purpose | Actual objective calls including fitter audit | Fitter elapsed seconds |
|---|---|---:|---:|
| 0 | LOW25 | 783 | 17.259 |
| 1 | LOW50 | 289 | 6.175 |
| 2 | HIGH25 | 728 | 15.141 |
| 3 | HIGH50 | 246 | 4.652 |
| 4 | LOW→full fixed | 1537 | 60.110 |
| 5 | HIGH→full fixed | 1529 | 60.061 |
| 6 | LOW→full free25 | 196 | 6.842 |

The bound is600 iterations, not600 objective calls. Independent audit/screen calls are additional and recorded. Every unit had an independent external195/200 second TERM/KILL bound, with at most four single-thread workers; waves completed in151.970 and48.264 seconds. The original-source budgets and new added search cost differ. Eight component tests passed, including actual native fixed-position KKT replay; two evaluator guards passed. A harmless import-spacing Ruff finding was retained in frozen driver bytes rather than editing source after freeze. Evaluator Ruff checks passed.

The next justified numerical control should preserve the best feasible training trajectory and attempt strict completion from that state under a separately declared matched budget. It must preserve this experiment and all failed outcomes; a stationary but much worse profile is not evidence against the better feasible basin.

Sources: transport qualification683f82e27; control03f3bfe88; evaluator7fe2c1923. Numerical namespace `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c053-half-transport-control-v1`; global seal SHA256 `08c3ae59715530b1e92fce13782a1c258b31a859ff2e3cf72203785634485156`. Configured comparison is adjacent `ds22-c053-half-transport-comparison-v1`. No held or locked observations were used.
