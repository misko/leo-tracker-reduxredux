# Persistent native prefix replay

The persistent worker accumulates the winning native GLRT candidates once and extends an exact SGP4 knot bank as the hardware sample counter advances. It stores orbit validity per knot so a bad later state cannot remove a satellite from an earlier prefix. Every checkpoint rebuilds Graph, local visibility, the Doppler shortlist, orbit assignments and both clock-calibration fits. Unsupported time layouts and changed satellite objects use the original projector.

The production-shaped entry is `python -m tools.pipeline_eval.qualification.prefix_reuse_worker`. It takes a bounded JSON initialization line with the original capture-start clock and immutable catalogue/configuration request, then one line per 120, 180, 240 or 300 s checkpoint with only the newly completed native visits. It emits one JSON result per accepted increment. Mounted inputs and their digests are verified on first use. The trusted producer owns authentication of archive GLRT bytes and incremental export. The sandbox receives neither the original capture file nor its future counters. Callers must preserve order and restart the worker to replay a session after interruption.

`replay.jsonl.gz` includes every fresh and persistent audited checkpoint, original hardware frontiers, exact observation digests, comparisons and timers. The separate persistent stopped run sends no increments after both arms choose. Its costs are compared with the measured fresh-worker subset through the same decision. Each worker uses the same 512 MiB address-space cap. Worker CPU excludes time spent awaiting new acquisition. Host worker wall includes framing and process startup where measured. Simulated acquisition-plus-compute delay uses delivery clocks and host measurements from this replay. It describes the stored native GLRT path on this host.

The first engineering attempt exposed a non-JSON NumPy integer in the instrumentation. The frozen replay converts this counter to a native integer and restarts both arms. The numerical projector was unchanged by that correction.

All 32 paired checkpoints matched their exact Graph observation digest, selected orbit/time support, and numerical results in both calibration arms. All eight cases made identical stop and publication decisions. Median cost through the actual stop was:

| Measure | Fresh workers | Persistent worker |
| --- | ---: | ---: |
| Sandbox CPU | 7.35 s | 5.41 s |
| Host worker wall | 11.51 s | 8.91 s |
| Native GLRT reads or frames | 41.55 MB | 17.98 MB |
| Orbital state evaluations | 472,426 | 203,400 |
| Native decode and peak selection CPU | 0.250 s | 0.155 s |
| Graph CPU | 2.98 s | 2.98 s |
| Orbit and clock backend CPU | 3.32 s | 2.73 s |
| Peak resident memory | 138 MiB | 171 MiB |

Each path published 6/6 matched roof positions per arm. Median position error was 0.835 km at zero c and 0.733 km with fitted c. Median RF RMS was 148.1 and 99.0 Hz, respectively. The existing rule falsely published both near-omitted controls in both arms, about 4.5–8.3 km from their roof references. The matched cases published at one 180 s, four 240 s, and one 300 s checkpoint in each arm. Persistent host completion at those checkpoints was about 186–302 s from capture start in the recorded-delivery scenario. These paired results qualify the reuse mechanism on eight recordings. A full 605-checkpoint replay was outside this pilot.
