# The North occupancy flip avoids a much worse fix and misses the accuracy gate

On the same frozen 224-visit blackout, the selected unfiltered route cut North’s horizontal error by **1.603 km fixed and 2.007 km fitted** relative to history. The fixed-arm error still exceeded named v3 by **394 m**, 144 m beyond the development allowance. Both routes produced complete outputs. The flip mitigates the accuracy loss on this intervention. It fails the frozen criterion for protecting both-arm accuracy. [Frozen protocol](selector-occupancy-position-protocol.md) · [Scored pair and complete evidence](measurements/selector-occupancy-position.json.gz)

| North containing route | Fixed / fitted horizontal error (km) | Fixed / fitted RF RMS (Hz) | Owners per arm |
|---|---:|---:|---:|
| Named v3, unperturbed | 0.106 / 0.141 | 5.406 / 5.167 | 302 |
| Unfiltered, unperturbed | 0.390 / 0.121 | 69.401 / 70.860 | 347 |
| History, unperturbed | 0.128 / 0.113 | 6.881 / 6.764 | 304 |
| Unfiltered, blackout | **0.500 / 0.105** | 67.266 / 68.288 | 351 |
| History, blackout | 2.103 / 2.112 | 9.601 / 9.601 | 26 |

Against each unperturbed route, the blackout changed errors by **+110/−16 m** unfiltered and **+1,975/+1,999 m** with history. The lower RF RMS of masked history accompanies much larger position error. Both fits use the original offered square, causal archive, Graph settings and numerical route. They reach the same 25-probe `inside_score` early decision. Unfiltered also reaches `inside_score` on its postfit exterior recheck. History’s postfit position does not trigger that recheck. [Unperturbed controls](north-causal-transfer.md) · [Exact coordinates, fit errors and geographic results](measurements/selector-occupancy-position.json.gz)

The original source has 2,400 antenna opportunities and 1,078 measured factors. The mask leaves **863 observed**, **215 erased positives**, **233 erased empty opportunities**, and **1,089 unmasked native empty opportunities**. History rejects **631** surviving factors and leaves 232. Unfiltered prepares 419 Graph points on 29 tracks, with 18 curved. History prepares 106 points on ten tracks, with two curved. All 26 history owners survive in the unfiltered case with the same satellites and roles, and unfiltered assigns 325 more owners per arm. Relative to unperturbed history, the blackout removes 278 owners without changing any of the 26 remaining owners or roles. [Per-opportunity ledger and ownership](measurements/selector-occupancy-position.json.gz)

| Blackout route | Numerical CPU (s) | Saved process CPU / elapsed (s) | Evidence |
|---|---:|---:|---|
| Unfiltered | 3.994 | 7.350 / 7.352 | 137 grid points, position path, eight PNGs |
| History | 2.542 | 5.448 / 5.450 | 137 grid points, position path, eight PNGs |

The installed scanner verified the original saved detector and retained its bytes exactly in each private output. The two numerically consumed rosters were explicitly unqualified, derived in memory only after the original handoff, and sealed separately with their projection digests. The original detector and scan report record the acquisition source. `RESEARCH-ONLY.json` and the scored evidence identify the actual fit input and record each erased and retained opportunity. The independent readback verified all final owners against their retained measured inputs, matched both complete grids and position paths to the terminal, and decoded all eight PNGs per run. Both calibrations had zero objective replay discrepancy. An initial worker stopped before preparing numerical inputs because an import preceded release startup. The corrected pair contains exactly the two planned saved solves. [Projection runner](selector_occupancy_position.py) · [Independent score](selector_occupancy_position_score.py)

This comparison applies one fixed detector-output intervention to one existing simulated waveform. It supplies no new RF receiver or different-location evidence. No waveform reads or further solves ran. Eleven focused and adjacent tests passed. [Crossed occupancy audit](selector-occupancy.md) · [Component checks](../../../tests/pipeline_eval/test_selector_occupancy_position.py)
