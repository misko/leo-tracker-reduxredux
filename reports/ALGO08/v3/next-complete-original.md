# DS30-0049 original-source enrollment and stopped backup copy

DS30-0049 was the smallest fresh input that fit the 20-minute copy envelope by original byte count. Its signed source contains **986 issued visits, 932 usable visits, 16 compressed members and 1,204,739,150 total original bytes**. A separate batch worker published a complete candidate directly from the original. The controller stopped the now-redundant guarded copy after **661.950 s**. The retained backup has **469,714,864 bytes in verified original files** and a **66,060,288-byte partial member**. The backup remains incomplete and was never used for a receiver or solver. [Protocol](next-complete-original-protocol.md) · [Custody, passive checks and copy events](measurements/next-complete-original-0049.json.gz)

## Enrollment and readiness

The metadata join used the 455-case signed DS30 manifest, the later input audit that pins each native job, and only opaque case membership from the release timing roster. The 512 original-window floor leaves room for the installed 20-second curvature condition at the standard scan cadence. The chosen recording has a **42.53–43.24 s** original observed interval on each RF lane. No detection score, owner, position estimate or evaluation reference informed enrollment. There were 436 metadata-eligible captures after the prespecified exclusions and the length floor. Eight fit the theoretical byte budget. The smallest remaining eligible release-panel source, DS30-0316, required at least **3.752 GB** including indexes, beyond the **2.517 GB** absolute limit at 2 MiB/s. DS30-0049 is outside that release subset.

The first dataset manifest calls this capture incomplete because the original scan stopped before finishing its schedule. The signed file list covers every window actually persisted by the original run. The retired initial eligibility check interpreted the recording-state label and the old native-availability flag as requirements. The corrected enrollment uses the later input audit's native bindings and the full signed coverage of physical extents. The protocol amendment was committed before any waveform read. No analysis outcome was opened.

At preflight the complete selected original had **1 of 294,147** signed pages resident, including zero in its first encoded member. A separate non-reading check found zero first-member resident pages on all eight size-eligible sources and DS30-0316. Their exact known NVMe paths were symlinks to the original backing directories. The precise temporary-root probes found no independent original copy. This covers the bounded shortlist and explicitly named paths. Process readiness for direct live reads did not require that those files be resident.

## Verified custody and deliberate stop

| Scope | Observed |
| --- | ---: |
| Guarded reads admitted | 526 |
| Measured admission wait | 400.906 s |
| Guarded bytes including original job, request and archived native | 536,381,550 |
| Original compressed bytes copied | 534,546,785 |
| Fully authenticated original files | Two manifests, original lifecycle, seven indexes and six complete compressed members |
| Partial compressed member | 66,060,288 / 78,230,196 bytes |
| Physical source cache at stop | 3,077 / 294,147 pages |

The partial member's last journaled prefix SHA-256 is `6bd8bede63d59a9b34d5f6dc63e21609ec3101c364d4864404e67b27f81362b0`. It lacks whole-member verification. The controller sent SIGINT in the post-read pacing sleep after the independent direct attempt had completed. The copy process wrote its ordinary exception cleanup receipt and exited 130. The separate custody seal records the stop reason and exact retained stage. Every new source read passed the original idle-admission helper and shared Gauss lock, at CPU2, nice 15, idle I/O, with at most 1 MiB per read and a 2 MiB/s pacing limit. Early storage queue samples exceeded the original threshold and the guard waited. No source paths or already-acquired files were deleted or moved.

Both staged manifest hashes reproduce the exact original path-bound inventory `sha256:8243d304e0429146a7f7349b906b464366a93fd4008b0b87506575ec21cfe9ff` and session `fast-8243d304e0429146a7f7349b906b4643`. The signed job's raw authority is `sha256:677da393a37dde5b39237e3284625b21fe64d7588938356d0ef05cd207f327d8`. The staged native control pins cutoff `1794620799057116515` and the authenticated request pins 48 earlier snapshots with archive digest `sha256:4fab883fc33b103ef4111bfcdf0ef6d0b07c069eea8fe976536fbb6b334c576e`. The backup did not reach its snapshot-body staging phase.

The separate direct workflow's generation-1 marker reported `complete` on the same session and causal archive, with terminal `sha256:50714e8c86b7b1616d03c190dea3306ea1822c74dd880cf436631fe4550fa03e`. The independent workflow validator confirmed both calibration arms, the 179-point grid and all eight PNGs. Its marker sits at `/srv/postgres-nvme/leo-ds30-evaluation-20261124/cases/DS30-0049/successor/attempt-000001/publication/algo08v3-successor-release.json`, SHA-256 `9f36426030b39868968d9e34d72b3ea51d33cc134c2e11a735c2ccd8dd107bce`. This confirms a complete direct-original workflow. The clean installed-versus-candidate comparison has a separate timing and scoring boundary.

The as-run stage was pinned by `878106bd6` and the stopped data remain under `/tmp/leo-v3-ds30-0049-complete-idle01/`. The expanded custody SHA-256 is `84d66d554e3653bddf87afaf48658ca4aca2b3dbf960f81ae0e347f12ca90dcc`. Eleven component tests covered the selection, signed inventory assembly, causal archive limits and idle-admission mechanics. [Selection](next_complete_original.py) · [Guarded staging](next_complete_original_stage.py) · [Passive check](next_complete_original_residency.py) · [Custody reader](next_complete_original_custody.py)
