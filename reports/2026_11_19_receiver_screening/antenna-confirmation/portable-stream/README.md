# Partner-on-hit portable replay

Four relocated services replayed complete saved I/Q through the stock four-region detector and the compact fit in both calibration arms. The one- and two-worker runs produced byte-identical native factors within each recording. Compared with the independent dual-RX stock projection and the previously measured direct partner-on-hit runs, every ordered observation, delivery clock and exclusion matched exactly. The portable factor identities are derived from observed rows, their detector and recording authorities, and their exclusions. Only the four declared lineage fields differ from the direct packet. Positions, RF RMS and the frequency objective match the direct runs exactly.

| Recording | Raw through factors, 1 → 2 workers | Full service, 1 → 2 workers | Visits ≤20 ms, 1 → 2 workers |
| --- | ---: | ---: | ---: |
| DS26-0168 · lower | 107.64 → 96.14 s | 173.53 → 146.78 s | 6,381 → 4,599 of 6,774 |
| DS29-0174 · upper | 139.54 → 150.21 s | 196.71 → 210.95 s | 4,657 → 1,404 of 6,704 |

Each service authenticated all 14 original segments and 6,774 scheduled visits. DS26-0168 had 9,260 physical detector calls, including 2,486 partners. DS29-0174 kept 70 capture exclusions and made 8,802 physical detector calls, including 2,098 partners. The counts were unchanged between worker configurations. The 20 ms column measures a valid visit's detector service, including its partner call when requested. The stage and full service clocks include their actual host-side dependencies. Two workers improved makespan on the lower recording and increased it on the upper. Each pairing provides one run per configuration under normal shared host load, with order reversed across the recordings.

All cgroups reached the 512 MiB charged-memory cap under raw replay and completed without swap or an OOM kill. Charged memory includes I/O cache. The compact position processes had 300–358 MiB peak RSS. Per-stage CPU, memory-cap events and host clocks are in the resource CSV. These are x86-64 host measurements.

Both worker counts produced 4.154 km geographic error in each arm on DS26-0168. DS29-0174 had 0.783 km at `c = 0` and 0.893 km with fitted `c`. The endpoint CSV includes raw coordinates and frequency measures on separate columns for both arms and both measured worker counts.

## Evidence and replay

- [Protocol](PROTOCOL.md) and [input lock](input-lock.json) bind the exact edge, raw segments, causal request, calibration arms, cores and order.
- [Prediction lock](prediction-lock.json) seals all four terminal services before either geographic or predecessor outputs were opened. The packaged receiver receives only each explicit [lower input](DS26-0168-input.json) or [upper input](DS29-0174-input.json), the CPU pair and the worker count. [Parity results](parity.json) bind both independent native authorities and exact outputs.
- [Stage PDF](resources.pdf), [timing data](resources.csv), [paired deltas](paired-resource-deltas.csv), and [position data](positions.csv) are bound by the [stage lock](stage-lock.json). The [portable usage instructions](USAGE.md) describe the runtime dependency and public entry.

The `tools.pipeline_eval.qualification.portable_stream_trial` module records `freeze` and `run` from the relocated release. The `tools.pipeline_eval.qualification.portable_stream_results` module records `seal` and `publish`. Use a separate workspace copy and fresh `--work` for a repeated four-service measurement. The `publish` action recomputes the tables and validates scientific parity from the sealed receipts and original archive manifests without replaying waveforms or fitting positions.
