# DS30-0163 first-member idle window ended without admission

The one **300 s** idle-only window stopped at **299.001 wall s** with
**35,651,584 of 78,720,466 encoded bytes** staged. The original
manifest, member index and staged prefix hash verified. The incomplete
member did not qualify for a receiver pair. No second window or
receiver worker launched. DS30-0173 stayed outside this operation.
[Frozen window](first-member-0163-idle-protocol.md) ·
[Earlier passive admission](ds30-combined-first-member-admission.md)

| Paid staging scope | Observed value |
| --- | ---: |
| Enrolled first member | 78,720,466 encoded bytes, 64 visits |
| Copied payload | **35,651,584 B**, 34 one-MiB reads |
| Copied signed metadata | 180,092 B in two admitted calls |
| Controller wall / CPU | **299.001 / 0.234 s** |
| Wait inside slots before admitted reads | 251.097 s |
| Idle-wait logs / stall-guard pauses | 37 / 0 |
| Longest admitted payload read | 33.9 ms |
| Process input blocks | 69,992 |
| Original resident pages before / after | 0 / 8,448 of 19,219 |
| Encoded bytes remaining | **43,068,882 B** |
| Receiver clocks or signed detection packets | **0** |

The unchanged quiet interlock took the Gauss lock only around each
permitted request and yielded between reads. The controller ran on
CPU 2 at nice 15 with idle I/O priority. Its 1 MiB requests used
random file advice to suppress sequential readahead and held the
2 MiB/s cap. Logged full I/O PSI avg10 peaked at **1.16%** while the
recent weighted dm-5 queue reached **19.35** and the instantaneous
in-flight count reached **79**. At 285.151 s, even uninterrupted
copying at the allowed rate needed **20.537 s** with **14.848 s**
remaining. The original one-second cutoff margin prevented another
request. The controller clock starts after Python imports and ends
after the final descriptor-only cache check.

The checkpoint owns a verified **34 MiB** prefix under
`/tmp/leo-v3-0163-first-idle-stage01`. Its independent digest is
`sha256:49429adbd0ca6ac5fbf47f1f14fef10a97a3a9487bf2fb893a9b6549f57a55c0`.
The local recheck also matched both original signed sidecars and read
no original payload. The full compressed digest, decoded member and
per-visit contents remain unverified. This window supplies no
resident receiver timings, stereo activity or comparable frequency
observations. The existing blind solver measurements use saved
detector packets and retain their separate scope.
[Saved DS30-0163 result](ds30-0163-combined.md)

The physical stage ran from
`4873232fe5ade740df7b7e7fb1fd88c7e158faf3` and verified the unchanged
shared interlock source before any data reads. Twenty component and
adjacent tests passed.
[Stage driver](first_member_0163_idle.py) ·
[Tests](../../../tests/pipeline_eval/test_first_member_0163_idle.py) ·
[Machine receipt](measurements/first-member-0163-idle.json.gz),
uncompressed SHA-256
`e6dfabaf402fd84179fe69d5f971a906258dd3446456cacc018a6cccff57a6a9`.
