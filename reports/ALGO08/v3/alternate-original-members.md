# Alternate original compressed members

**DS30-0163 failed the 250 m accuracy screen in both arms.** With every other signed compressed member omitted, the position errors increased by 1.157 km at `c = 0` and 1.187 km with fitted `c` against the matching full-20 ms composed solver. DS30-0016 passed its separate development screen against the installed full-20 ms solver. Both candidates completed with all 179 grid points, both endpoint samples, a bound position path and eight independently decoded PNGs. [DS30-0163 protocol](alternate-original-members-protocol.md) · [DS30-0163 evidence](measurements/alternate-original-members-0163.json.gz) · [DS30-0016 protocol](alternate-original-members-0016-protocol.md) · [DS30-0016 evidence](measurements/alternate-original-members-0016.json.gz)

| Case and input | Error, `c = 0` / fitted `c` | RF RMS, `c = 0` / fitted `c` | Fitted minus zero score at the respective endpoints |
| --- | ---: | ---: | ---: |
| DS30-0163 full composed | 0.982 / 0.854 km | 135.158 / 135.046 Hz | −2.865 |
| DS30-0163 full installed | 0.989 / 0.859 km | 135.159 / 135.047 Hz | |
| DS30-0163 alternate members | 2.139 / 2.042 km | 135.325 / 135.453 Hz | −0.021 |
| DS30-0016 full installed | 1.644 / 1.661 km | 109.375 / 109.479 Hz | +10.022 |
| DS30-0016 alternate members | 1.582 / 1.534 km | 99.780 / 99.832 Hz | +10.009 |

Within the masked DS30-0163 input, fitting `c` reduced horizontal error by 97 m while RF RMS increased by 0.128 Hz. Within the masked DS30-0016 input, fitting `c` reduced error by 48 m while RMS increased by 0.052 Hz. The masks change the number of likelihood terms, so the raw score magnitudes across full and masked inputs cannot rank their location accuracy. Both cases used the same 81 coarse coordinates as their controls and the original 49-point sampling around each arm's own endpoint. [DS30-0163 evidence](measurements/alternate-original-members-0163.json.gz) · [DS30-0016 evidence](measurements/alternate-original-members-0016.json.gz)

| Case | Retained / original signed members | Retained / issued stereo visits | Retained / original processed stereo visits | Retained / original factors | Retained / original compressed bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS30-0163 | 53 / 106 | 3,392 / 6,772 | 2,659 / 5,330 | 1,858 / 3,731 | 4,185,851,415 / 8,356,273,818 |
| DS30-0016 | 7 / 13 | 424 / 808 | 376 / 713 | 220 / 440 | 520,356,006 / 991,734,597 |

The mask applied parity to the signed chronological member ordinal across segment boundaries and used each member's declared visit span. It preserved both receiver slots and the full timeline. The private receipts distinguish the 3,380 and 384 unmeasured visits from the 733 and 48 original invalid captures inside retained members, respectively. For DS30-0163, the policy could avoid reading 49.91% of compressed payload bytes and up to 50.11% of nominal full-20 ms detector calls if validity stayed fixed. For DS30-0016 the corresponding fractions are 47.53% and 47.27%. Those are work counts from the signed inventory and original detector ledger. [Member and visit projection](alternate_original_members.py)

DS30-0163 took the original `lean` route with healthy samples and one inference call. The same Graph implementation ran once, with 73 tracks and 1,388 assigned observations versus 117 and 3,439 for full composed. In each calibration arm, 1,205 of 3,055 original owner IDs persisted, three were added, 1,850 were dropped, and 37 shared IDs changed role. No shared ID changed satellite. All 356 native grid selections and reduced likelihood evaluations ran, along with both fixed Agg orbit renders and eight native PNG checks, with no fallback. DS30-0016's installed ordinary route retained 52 of 109 owners in each arm without changed roles, reassignments or added owners. [DS30-0163 evidence](measurements/alternate-original-members-0163.json.gz) · [DS30-0016 evidence](measurements/alternate-original-members-0016.json.gz)

| Case and clock boundary | Child wall / CPU | Wall / CPU including available setup |
| --- | ---: | ---: |
| DS30-0163 alternate members, saved | 14.537 / 14.408 s | 15.273 / 15.076 s |
| DS30-0163 full composed, historical saved | 11.025 / 10.888 s | 11.630 / 11.444 s |
| DS30-0163 installed, historical saved | 20.767 / 20.745 s | 22.598 / 22.249 s |
| DS30-0016 alternate members, saved | 6.425 / 6.305 s | 7.043 / 6.776 s |
| DS30-0016 installed, historical raw to publication | 10.861 / 10.855 s | |

The smaller DS30-0163 saved solve took 3.512 s longer in elapsed time than the historical full composed saved solve. The DS30-0016 historical installed clock includes waveform ingestion and detector work, so it does not provide a matched saved speed comparison. Both paid saved solvers used one low-priority CPU 2 core. No waveform, index, backing catalogue or new RF was opened by the trial workers. [DS30-0163 clocks](measurements/alternate-original-members-0163.json.gz) · [DS30-0016 clocks](measurements/alternate-original-members-0016.json.gz)

DS30-0016 ran while the full set of DS30-0163 manifests was unavailable. Once local authenticated copies were available, the first DS30-0163 child stopped at admission in 1.399 s wall and 1.350 s CPU. It handed the masked packet digest to one read port while the other port reopened the full original request. The repair persisted a derived request whose packet digest and source authority agreed across ports. One authorized scientific child then ran the frozen policy. In the isolated checkout, the repaired run used the earlier `two_centre_seeds.py` bytes from `4a90b3509`, as pinned by both full composed admissions. The DS30-0016 scorer also had to include the stock control's separately sealed `process-context.json`. That verification fix preserved the sealed candidate and scoring thresholds. [DS30-0163 admission failure](measurements/alternate-original-members-0163-admission-failure.json.gz) · [DS30-0163 adapter](alternate_original_members_0163.py) · [DS30-0016 scorer](alternate_original_members_score.py)

The searched report and source history contained alternating archived sweeps, per-RF alternating visits and a first-third contiguous replay. Those studies select by visit order or channel. The search found no previous measured replay keyed to the original signed compressed members. The present mask also acts after full 20 ms temporal processing, so retained factors can carry continuation state from omitted members. A genuine acquisition candidate needs a supported skipped-acquisition contract and provenance binding the signed member inventory, receiver execution and full clock ledger, plus a raw replay restricted to the retained members. The DS30-0163 result rules out adopting the unconditional policy on this evidence. [Archived sweep schedule](../../../tools/pipeline_eval/variants/sweep_schedule.py) · [Per-RF receiver cadence](../../../tools/pipeline_eval/variants/experimental/receiver_cadence.py) · [Contiguous first-third replay](contiguous_third.py)
