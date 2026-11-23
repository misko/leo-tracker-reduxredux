# Refine CFO after the short receiver establishes ownership

On saved North containing, post-owner refinement preserved all **347** original ordered owners per arm and returned **110 m fitted error**, compared with **122 m** unrefined and **533 m** when the same refined measurements entered before Graph. Fixed-zero error moved from **388 to 401 m**. On physical DS30-0016 the post-owner result preserved all **116** original owners and improved fixed/fitted error by **296 / 163 m**. Both original paired gates accepted the updated fit. [Protocol](owned-cfo-protocol.md) · [Both complete saved receipts](measurements/owned-cfo.json.gz)

| Saved detector views and solver ordering | Fixed / fitted horizontal error (km) | Fixed / fitted RF RMS (Hz) | Owners per arm |
|---|---:|---:|---:|
| North original short | 0.3880 / 0.1216 | 69.400 / 70.860 | 347 |
| North refine before Graph | 0.3598 / 0.5334 | 75.601 / 77.297 | 265 |
| North refine after ownership | **0.4010 / 0.1101** | 69.820 / 71.307 | 347 |
| DS30-0016 original short | 1.3110 / 1.6940 | 121.526 / 120.291 | 116 |
| DS30-0016 refine before Graph | 1.0098 / 1.5577 | 118.260 / 117.490 | 116 |
| DS30-0016 refine after ownership | **1.0152 / 1.5309** | 118.385 / 117.600 | 116 |

The North comparison uses one previously scored public simulation and its containing offer. The weak comparison uses one physical recording. The post-owner North fixed-zero result remains outside the earlier +250 m envelope against named v3. These runs did not test an omitted offer. Fitted error improves on both cases. North RF RMS rises in both arms despite its fitted position improvement. [Upstream North receiver transfer](raw-cfo-north.md) · [Upstream physical receiver transfer](raw-cfo-0016.md)

## The same measurements, applied after discovery

The two authenticated receiver views for each case share raw authority, inventory, lane membership, phases, ranks, scores and margin flags. Their only measurement difference is the signed CFO measured by the frozen fixed-epoch waveform refinement. The saved stage starts with the original short detector packet. Graph, noise, association, support acceptance and the original published roster all use that short view. Once both accepted arms have an identical roster, the policy looks up owned IDs in the second receiver view. It preserves the original pointwise and track aliases, ownership masks, satellite and role, original phase prior and the short-derived noise weights. It makes a separate track and observation view for the released five-round final numerical refit in both calibration arms. Selection uses the accepted common owner IDs and the two same-receiver input views.

The original pair and exterior gates still run. The exterior corroboration deliberately keeps the discovery view. If paired compatibility, exterior or complete evidence fails, the existing post-fit port retains the incumbent. No measured fallback was needed here. A component check verifies that changing the trial's track and presentation values leaves the original available for fallback. The paired evidence contains the exact revised measured CFO for all **302 North and 96 weak** changed owners in each arm. Every other published observation retains the original measurement. The numerical grid and position path bind the actual revised position PNG. North evaluated all 137 planned grid points and weak all 179. All eight PNGs per run were independently decoded and hashed, with zero endpoint objective replay difference in both arms. The separate diagnostic receipt binds both input detector digests to these artifacts. [Policy](owned_cfo_finish.py) · [Saved runner and verification](owned_cfo_trial.py)

## Cost and retained input

| Measured boundary or input count | North | DS30-0016 |
|---|---:|---:|
| Positive short lanes / distinct positive stereo visits | 996 / 623 | 401 / 322 |
| Owned short lanes / changed CFOs in both arms | 303 / 302 | 101 / 96 |
| Clone and bound the changed measurements, CPU s | 0.0008 | 0.0003 |
| Two original final arm refits, CPU s | 0.1067 | 0.0541 |
| Follow-up exterior check, CPU s | 0.2535 | <0.0001 |
| Entire saved numerical solve, CPU s | 4.160 | 2.564 |
| Whole saved process, elapsed / CPU s | 6.646 / 6.472 | 4.643 / 4.636 |
| Full original CI16 retained by stereo visit, decimal MB | 996.8 | 515.2 |
| Full original CI16 packed by positive lane, decimal MB | 796.8 | 320.8 |

The actual waveform measurements came from the sealed raw runs. They spent **0.900 and 0.319 CPU s** to attempt refinement on all 996 and 401 positive short lanes. The new saved runs perform no waveform read or refinement kernel call. Pricing only the eventual owner attempts at each historical all-positive mean gives **0.274 and 0.080 CPU s** respectively. Including the measured clone, paired refit and follow-up exterior raises the estimated treatment cost to roughly **0.635 and 0.135 CPU s**. This estimate leaves the old expensive-vs-cheap outcome mix unchanged, although owned lanes are more likely to produce accepted refinements. It excludes buffer filling, eviction, deferred decoding and any load-related change to the numerical budget. It does not compare raw process times. The retained-input counts describe full input through the existing stereo interface or a hypothetical packed-lane interface. Owner IDs are unknown at that point, so retention must cover the earlier positive set or obtain it later. This option still needs a cheaper retention or re-access design and an end-to-end measurement before it can claim a raw speedup.

Run `owned_cfo_trial.py launch north|weak NEW_TMPFS_ROOT` and then `score` against that root with local scientific tools, under the shared Gauss lock on CPU 2, nice 15, I/O priority 7 and one numerical thread. The workers use metadata-only inventory and block waveform construction. Only one new saved solve ran per case. Four component tests passed. North and weak numerical seal SHA-256 values are `933eccbd307e832148fdb028ba06b651b89bd8e6e4d222b52fa97268b247759a` and `59794fecb9ba03db2ffa5979fa8643eea0b9d1b09e9069410a6c9b3173102d21`. [Tests](../../../tests/pipeline_eval/test_owned_cfo.py)
