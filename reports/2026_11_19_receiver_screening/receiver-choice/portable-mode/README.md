# Optional staggered detection in the portable receiver

The downloadable receiver keeps stock as the default for existing saved-IQ manifests. Select `--detector staggered` to give one physical receiver the fifth-center search per valid visit while the other uses the stock search. The same compact phase-release receiver consumes the resulting native packets. [Download the new bundle](portable-receiver-staggered.tar.gz) · [Usage](USAGE.md)

The relocated application reproduced the hard native program’s complete projected packet digests and selected receivers on **96 authenticated 20 ms visits**, 48 on DS26-0197 and 48 on DS29-0316. Each recording covered eight exact RF centers. The code keeps one counter per recorded integer target RF, starting at receiver zero. It advances only when the existing capture validator admits a visit to the detector. The two sampled intervals shared their counter state within each recording. All 96 sampled visits were valid. A component test checks the invalid-visit behavior. These measurements cover detector packets on bounded recorded subsets. [Parity ledger](parity.json) · [Frozen scope](PROTOCOL.md)

| Recording | Hard source → relocated wall, s | Hard source → relocated CPU, s | Hard source → relocated peak RSS, MiB |
|---|---:|---:|---:|
| DS26-0197 | 4.16 → 4.55 | 2.79 → 2.95 | 192.0 → 191.2 |
| DS29-0316 | 5.13 → 9.86 | 2.86 → 3.16 | 192.5 → 191.4 |

These are single host stage replays on CPUs 6 and 7 at nice 10. Wall includes invocation, startup, decode and the native calls, with the measured scheduling delays. CPU and RSS come from the actual receiver process. A provisional outer accounting tool failed to capture those two values through the relocation namespace, so the same bounded trials were repeated with process-owned counters. The rejected values are preserved. [Stage plots](mode-resources.pdf) · [Measured values](mode-resources.csv) · [Provisional outer accounting](preflight-resource-accounting.csv)

The new release has 214 application assets totaling 10,032,997 bytes, up from 201 and 5,109,596 bytes. Two exact native libraries account for 4,879,320 of the additional bytes. The chronological reader adapter, RF counter and Python wrappers account for 44,081 bytes. The original stock detector, acquisition code and position assets remain byte-identical. Python requirements and system runtime libraries are the same as for the stock portable release. The downloadable archive is 3.45 MiB. [Footprint breakdown](footprint.json) · [Resource and bundle seal](result-lock.json)

The bounded run used a separate wheel environment, with the source checkout and original native build directory masked. The saved capture inputs remained read-only. The package accepts the same caller-supplied local files as the stock release. This stage study generated no new geographic estimates. [Application file ledger](release-files.json)
