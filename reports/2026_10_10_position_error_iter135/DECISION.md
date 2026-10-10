# Clean phase timing replication: extend the test, do not deploy yet

The clean replay reproduces the earlier fitted-c improvement while removing
the legacy reference-error admission dependency. All twelve consumed pilot
recordings completed all four fits; all 48 passed the unchanged independent
convergence gate. Known receiver coordinates were read only after every member
was terminal. This is a controlled replication on development data, not new
independent validation or a full-cohort improvement.

![Position comparison and distributions](comparison.png)

| Arm / model | Mean km | Median km | p95 km | Worst km |
|---|---:|---:|---:|---:|
| Fitted-c timestamp control | 1.117359 | 0.905836 | 2.501273 | 3.389263 |
| Fitted-c orbital phase | 1.033639 | 0.807675 | 2.254102 | 3.326299 |
| c=0 timestamp control | 1.280581 | 0.826722 | 2.915394 | 4.193248 |
| c=0 orbital phase | 1.195908 | 0.935994 | 2.703730 | 3.763887 |

Fitted-c mean improves by 7.49% and median by 10.84%. Nine members improve and
three regress: DS17-015 (+75.9 m), DS18-013 (+32.2 m), and DS18-024 (+109.1 m).
The c=0 mean improves by 6.61%, but its median worsens by 13.22%; eight improve
and four regress, with a maximum regression of 191.8 m. These mixed results
must remain visible rather than choosing models separately for individual scans.

| Dataset pilot | Members | Fitted-c control mean km | Phase mean km |
|---|---:|---:|---:|
| DS16 | 4 | 1.026534 | 0.856103 |
| DS17 | 4 | 0.867977 | 0.785180 |
| DS18 | 4 | 1.457567 | 1.459634 |

DS18's mean is slightly worse, despite lower worst-case error. The twelve-member
average therefore does not establish improvement across every dataset. The next
position test should apply this one unchanged physical model to the full frozen
193-member development cohort, including all 63 DS16 members and all recorded
failures. It must preserve the latest recovery baseline and use matched controls,
banks, observations, priors and starts. Preparation for that extension is separate;
no full193 phase result is claimed here.

The phase model interprets satellite-specific relative timing as displacement
along an orbit, compensating the Earth-orientation shift that would accompany a
literal timestamp change. Common timing retains its timestamp interpretation.
No fitted parameter, prior or satellite bank is added. This tests a physical
interpretation; it does not prove that the timing offsets measure true orbit error.

All four fits start from the ordinary fitted-c endpoint, with only the existing
RF locks applied to c=0. This differs from iteration130's arm-specific starts.
The historical c=0 archive mean is 1.255968 km; the correct experimental comparator
is the fresh 1.280581 km timestamp control. Fitted-c phase errors agree with130
within 0.000000131 km, consistent with numerical reproducibility. The earlier130
execution remains diagnostic; this clean replication does not rewrite its history.

Frequency fit changes are small: median posterior RMS goes from 59.940 to
59.787 Hz fitted-c, and from 107.641 to 107.574 Hz for c=0. Score components,
assignment/support changes, qualification diagnostics and per-member regressions
are separate in the [full report](RESULTS.md) and [evaluation](evaluation.json).
Lower in-sample frequency score does not establish position accuracy.

Summed member runtime is 309.645 seconds, including reconstruction. Median phase
fit time is about 5.24 seconds fitted-c and 5.18 seconds c=0 in this research
implementation. The timestamp controls start at already fitted endpoints, so
their shorter times are not a fair estimate of end-to-end pipeline overhead.
No new RF collection, retry, fallback or production change occurred.

The published full193 fitted-c mean remains **1.254810 km** from iteration107.
The **0.4 km goal remains unmet**. Search-region recovery and the separate
residual-correlation diagnostic continue; neither is combined with these pilot
numbers to manufacture a new full-cohort result.
