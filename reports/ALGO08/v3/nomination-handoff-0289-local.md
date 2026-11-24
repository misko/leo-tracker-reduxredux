# Frozen routed solver on blind DS30-0289

The unchanged routed candidate fixed the third enrolled case in
**26.770 wall s**. Installed ALGO08v3 withheld at **18.820 s** with
`gate_refit_unstable`, exactly reproducing its archived decision.
The new fix was **1,616.150 m** from the reference at fixed zero and
**1,541.958 m** with fitted `c`. The two independently assigned
cases now have **2/2 routed fixes versus 1/2 installed**, with
**1.325×** speedup by summed saved-worker wall time. The sum includes
the shorter installed withholding on 0289. [Frozen rank-three protocol](nomination-handoff-0289-protocol.md) ·
[Earlier blind case](nomination-handoff-0419-local.md)

## Authenticated input and paid timings

The original 20 ms packet, inventory, 25 km operator offer and causal
cutoff verified from the release pins. The packet contains **6,774
issued**, **6,738 admitted**, **13,476 radio probes** and **6,824
factors**. The worker estimate under the original rule was **42.208 s**.
The local OS NVMe collector supplied all **46** original catalogue
files, totaling **82,190,541 bytes**. Their filename roster matched
`sha256:87b0e02bef4ef7541ca01caf25bf8a95ef71121f1fb72b47ad6b0753a5811f73`.
The stage checked the selected device and inode, extent and every
body SHA-256. Both workers used the same fully resident tmpfs copy.
Linux charged 82,452,480 input bytes to the local copy process.
Neither original waveform nor the backing archive was opened.

| Paid scope | Wall s | CPU s |
| --- | ---: | ---: |
| Local collection metadata and roster verification | 0.010 | 0.002 |
| Verify and stage all catalogue bodies | 0.205 | 0.063 |
| Common admission, including these two scopes | **0.869** | **0.605** |
| Routed regional preparation, inside solve | 2.857 | 2.857 |
| Routed numerical solve, including preparation and 179-grid | 22.831 | 22.805 |
| Installed numerical solve through withholding | 17.294 | 17.289 |
| Routed official publication, including solve | 25.340 | 25.304 |
| Installed official publication, including solve | 17.506 | 17.501 |
| **Routed child through verified exit** | **26.770** | **26.704** |
| **Installed child through verified exit** | **18.820** | **18.814** |

The odd-ID rule assigned routed first. Both saved workers ran in the
same low-priority CPU 2 lease, nice 15, best-effort I/O priority 7,
with one numerical thread. Both exit codes were zero. The routed
process recorded 1,000 input blocks and 21 major faults without
file-level attribution, while installed recorded zero of each.
The named preparation time is included in solve and has no separate
clock. The archived **92.380 s** installed raw total includes
acquisition and stays outside the saved comparison.

## Repair, guard, and published evidence

Healthy orbit samples selected the lean route. Cold nomination
took **6.532 wall s** and raced the winner. The geometry guard and
checkpoint attempt took **14.3 and 5.8 ms CPU**. The eight ranked
nodes were available, but the three complete prefixes were not.
The guard recorded one incomplete prefix set and no reuse.

The first paired fit rejected two curved tracks in each arm. One
ordinary paired support repair removed **51 of 3,410 curved
observations**, **11 of 1,099 predictive observations**, and
**three of 141 tracks**. Repair preparation and both refits took
**0.382 and 0.689 wall s** and both arms then qualified. The lean
attempt through repair took **13.484 s** in all, and standard
numerical evidence cost another **6.225 s**. It completed without
a named fallback or additional orbit-support knots. Neither final
position touched the boundary that triggers far probing.

| Calibration | Installed | Routed horizontal error | Routed conditional RF RMS |
| --- | --- | ---: | ---: |
| Fixed zero | Withheld | **1,616.150 m** | **105.724 Hz** |
| Fitted | Withheld | **1,541.958 m** | **105.721 Hz** |

The recovered candidate used the same **4,447 ordered observation,
satellite and role rows** in both arms, including 3,359 curved and
1,088 predictive observations. Fitting `c` reduced horizontal
error by **74.192 m** and RF RMS by **0.0024 Hz**. Both candidate
arms have complete 179-point grid scores and zero endpoint objective
replay difference. The verified grid and path bind the correct
position PNG, and all eight PNGs decoded and matched their own
digests. The reproduced installed terminal was byte-identical in
its signed representation, with committed null positions, no
ownership rows, grid, path or PNGs. There is no installed geographic
or RF error to subtract on 0289.

## Two blind cases

| Case | Installed through exit | Routed through exit | Installed / routed decision | Candidate geographic difference, fixed / fitted |
| --- | ---: | ---: | --- | --- |
| DS30-0419 | 38.072 s | 16.178 s | Fix / fix | −573.349 / −581.761 m |
| DS30-0289 | 18.820 s | 26.770 s | Withhold / fix | Unpaired, routed absolute errors 1,616.150 / 1,541.958 m |
| **Total** | **56.893 s** | **42.948 s** | **1/2 / 2/2** | One paired position comparison |

The reciprocal of the median paired candidate/installed wall ratio
is **1.083×**. Charging each common admission gives **58.523 /
44.578 wall s**, or **1.313×** by summed time. CPU through exit totals
**56.824 / 42.841 s**, or **1.326×** summed and **1.085×** by the
reciprocal median ratio. The two blind observations exercise the
unchanged full composition with no checkpoint reuse. DS30-0255
remains separate development evidence. Its measured successful
handoff took **56.232 s** against **50.721 s** for installed, with
equal fixed-zero and fitted accuracy. [0255 development](nomination-handoff-0255.md)

The launch froze in `b6b67c3f4bb67b65df7d9adc8c6a0b8148ba3d4a`.
The scientific worker pins matched the original remediation. After
prediction seal `4977e485fed90a7000aceb530f0d91e28967ea4fc7b10423e18b675a13f60aa2`,
the first scorer expected owner rows for the installed withholding.
The corrected scorer verified zero ownership for withheld arms and
rescored the sealed products. Neither worker was repeated. Twenty-five
tests passed. [Driver](nomination_handoff_0289_local.py) ·
[Tests](../../../tests/pipeline_eval/test_nomination_handoff_0289_local.py) ·
[Full receipt](measurements/nomination-handoff-0289-local.json.gz),
uncompressed SHA-256
`bef06fcc3d7c52d4268485e8ee211f45a30710e62ea7a38a8f8a58cef2eb3973`.
