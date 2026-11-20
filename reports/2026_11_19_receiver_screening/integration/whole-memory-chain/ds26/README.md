# DS26-0036 under one 512 MiB cgroup

The second service finished all 6,769 saved-IQ visits and reproduced the 22.5 MB ordinary factor file byte for byte. It was OOM-killed at signed context while running the row-major compact solver, before either position was returned. The kernel reported **536,870,912 bytes** of peak cgroup memory with a zero swap limit. The service ended at **11:54:22 UTC**, before the original 11:54:43 UTC cutoff. A pre-cutoff extension had been declared and the existing run ended before it was needed. [Cap and stage evidence](stages.json.gz) · [Cutoff snapshot](../panel-cutoff.json) · [Position chart](plots/README.md)

| Stage | Wall (s) | Cgroup CPU (s) |
|---|---:|---:|
| Authenticate, decode and detect | 129.791 | 235.819 |
| Assemble and bind position | 0.907 | 0.890 |
| Complete service, including failed position attempt | 182.629 | 288.153 |

Both ordinary lanes ran at nice 10 with one numerical thread on CPUs 18 and 19. They authenticated 106 compressed members across 14 segments and decoded 10.8304 GB. Of 6,769 visits, 6,765 ran the ordinary native analyzer and four were capture exclusions. Median and 95th percentile native-call wall times were 29.475 and 39.882 ms, with median CPU time of 28.645 ms. Fifty calls completed within the 20 ms visit duration. The 299.996 s acquisition span gives a 0.433 raw-stage ratio. The cap terminated the full attempt before a position, so those times quantify raw and partial solver throughput. [Raw lane and service counters](stages.json.gz)

The final marked solver stage was entry to `signed_context`, following completed conservative recovery, family confidence and history policy. The trace does not identify an individual allocation inside signed context. The recovered ordinary factor digest is `41b74326231d17abcc1ed6e8cfd37574a2f5752c366bc1e8b959c39c1ec5f94e`. The sealed ordinary tiled-salvage numerical control remains a separate completed result. Its endpoints and conditional Doppler fit were excluded from the capped outcome. [Capped no-fix rows](scores.csv) · [Ordinary compact control](../../../recovery/solver-memory/README.md) · [Input and prediction lock](prediction-lock.json)
