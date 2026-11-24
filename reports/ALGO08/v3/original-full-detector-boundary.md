# Full original detector publication boundary

One fresh 13-member DS30-0016 run reached the prefix study's detector commit in **5.053 s** and exited in **5.102 s**. The complete detector bytes equal the earlier normal verify-once publication. The two frozen 1→4 predictions for this hook were **3.392 s** and **3.372 s**. The archived normal run wrote the same detector payload at **4.678 s**. It spent **0.778 s** from the held-selector receipt to the standard detector file, versus **0.0025 s** for the early commit. The new run was slower during acquisition itself, enough to outweigh that boundary difference. [Frozen protocol](original-full-detector-boundary-protocol.md) · [Measured receipt](measurements/original-full-detector-boundary-0016.json.gz)

## Common boundary and observed costs

| Seconds from launch or within stage | New full detector-only hook | Archived normal verify-once child |
| --- | ---: | ---: |
| Launch to outer receiver acquisition | 0.330526 | ~0.338571 |
| Authenticated outer acquisition, elapsed | 4.668507 | 3.514017 |
| Inner acquisition, elapsed / CPU | 4.666094 / 4.661902 | 3.508810 / 3.508638 |
| Held-selector call, elapsed | 0.048985 | 0.047226 |
| Launch to held-selector file mtime | 5.050419 | 3.899813 |
| Held-selector file to detector file mtime | 0.002482 | 0.778170 |
| Launch to detector file mtime | 5.052901 | 4.677983 |
| Launch through immutable hook return | 5.053483 | — |
| Detector-to-exit residual | 0.048339 | 3.369991 |
| Process exit, elapsed / CPU | 5.101821 / 5.088351 | 8.047974 / 8.046283 |

The archived estimate for launch to acquisition subtracts the archived outer acquisition and selector-call elapsed clocks from the selector file clock. It includes any time between the two instrumented stages and omits any selector work after its file mtime. The archived phase receipt separately records 0.284943 s from bootstrap entry to receiver readiness and 0.006484 s for asset and inventory checks. The new run measured 0.007846 s within the base runtime loader and 0.002413 s from outer acquisition return to selector entry. The common selector-file boundary differed by 1.150606 s, while inner acquisition differed by 1.157284 s. The full-scope selector used the same source, chose the same unfiltered branch, and accounted for about 2 ms of elapsed difference. [Normal verify-once evidence](legacy-verify-original.md)

The two prefix experiments substituted a bounded research inventory and bounded traversal. The full diagnostic used the normal inventory, source verifier, receiver callback and held-history selector, with the same measurement hook extracted verbatim from the prefix harness. Seven shared entry, verifier, acceleration, receiver, selector and publication modules were byte-identical to the archived normal checkout on inspection. The hook commits standard immutable JSON at the call that would start the decision stage. Normal execution evaluates the empty-factor guard and active graph proof, builds the authenticated handoff, loads and configures the exact history-risk publisher and registered ports, then reaches the scanner's standard inventory/workspace checks and detector-file commit. The archived graph proof examined 16 lanes and selected the active path. The scanner's acquire callback consumes the existing handoff once, without another waveform traversal. The archived 0.778 s measures these operations together, including the ordinary file write. Its receipt has no disjoint import, graph-proof or publication-preparation clock before that write. [Bootstrap call order](unified_short_bootstrap.py) · [Normal publisher](exact_named_raw.py)

## How much the prefix prediction missed

| 13-member scope | Frozen 1→4 prediction | Frozen 4→1 prediction | New full hook | Archived normal |
| --- | ---: | ---: | ---: | ---: |
| Launch to signed detector, s | 3.392140 | 3.372163 | 5.053483 | 4.677983 |
| Inner acquire elapsed, s | 2.977574 | 2.976572 | 4.666094 | 3.508810 |
| Inner acquire CPU, s | 2.979239 | 2.976476 | 4.661902 | 3.508638 |

Even the earlier normal child, which incurred no major faults or input blocks, took **0.531–0.532 s** longer in inner acquisition than the prefix fit forecasts. Adding the archived 0.778 s publication interval to either prefix prediction gives **4.150–4.170 s**, still **0.508–0.528 s** below its actual launch-to-detector clock. The comparison supports both a scaling shortfall and a later publication boundary. The 13-member measurements through each detector boundary correspond to **196.2 MB/s** in the new hook and **212.0 MB/s** in the archived normal child. They do not establish a 280.5 MB/s complete-recording result or a geographic outcome on DS30-0419. [Measured prefix orders](original-prefix-scaling.md)

The new hook child incurred **1.977 s system CPU**, **3,376 process input blocks** and **21 major faults**. The archived normal child's whole-process values were **1.110 s**, **0** and **0**. The sums of reported encoded-authentication CPU were **0.608 vs 0.245 s**, native direct-to-owned decode CPU **1.109 vs 0.925 s**, and detector native CPU **1.831 vs 1.753 s**. Decoded-hash CPU was **0.147 vs 0.328 s**, while its elapsed clock was **0.401 vs 0.328 s**. These counters cover different receiver scopes and include process activity from the normal lookahead thread. Their deltas are descriptive. The single diagnostic cannot assign the entire extra acquisition time or the process-level input blocks to particular code or files.

## Input and exact outcome

The existing read-only tmpfs mount presented the genuine signed recording directory. All **242,675 pages** of its 28 enrolled payload, index and manifest files were resident before and after the child. The original metadata and encoded-authentication scopes recorded **zero input blocks**. The run checked **991,734,597 original compressed bytes**, the complete original member/window/index digests and ordered **808 issued visits**, including **95 exclusions**. It emitted **1,426 ordered signed probes** and **506 selected factors**, giving the same full bytes as standard publication with SHA-256
`aeb4658b886daaa4f8a93e99224fb4471f032f91feaa5ce58be2361d7009b4ac`.
The diagnostic performed no solver, positioning or rendering work.

## Reproduction

Run the research launcher `original_full_detector_boundary.py launch FRESH_TMPFS_DIR` with the installed release Python and the enrolled private read-only bind, under the shared CPU2 lock at nice 15 with best-effort I/O priority 7 and one numerical thread. It admits only the earlier original receipt and the frozen prefix scores by hash. Run `score FRESH_TMPFS_DIR` offline after exit. The as-run source commit was `0bb425c94`. The first offline score treated the whole-process input counter as an original-payload counter. The corrected scorer gates on the original member read counters and preserves the whole-process value in the receipt. It reused the one successful acquisition without relaunch. The focused and adjacent suite passed all 32 tests. The checked uncompressed result SHA-256 is
`dab95968e83696d5c7dc66443bca3b6923971cfa119e556f765a4b7b4c01a1be`.
