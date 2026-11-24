# DS30-0419 first-member idle staging expired

One **120-second** idle-only opportunity stopped at **119.404 wall s**
with **18,874,368 of 79,163,761 compressed bytes** staged. The signed
index and original manifest both verified. The staged payload remains
an incomplete compressed member. Neither receiver worker ran, so the
resident analysis has no timing, factor or CFO observations.
[Original cache-only deferral](first-member-0419.md) ·
[Idle staging amendment](first-member-0419-idle-protocol.md)

| As-run scope | Value |
| --- | ---: |
| Required first member | 79,163,761 encoded bytes, 64 visits |
| Copied encoded prefix | **18,874,368 B**, 18 one-MiB requests |
| Paid signed metadata | 180,551 B, two admitted calls |
| Process input blocks | 37,224 |
| Controller wall / CPU | **119.404 / 0.098 s** |
| Interlock wait preceding admitted reads | 108.391 s |
| Logged idle waits / stall-guard pauses | 16 / 0 |
| Longest admitted payload call | 12.9 ms |
| Original payload page cache before / after | 0 / 4,608 of 19,328 pages |
| Encoded bytes still missing from the stage | **60,289,393 B** |
| Resident receiver starts / signed detection outputs | **0 / 0** |

The unchanged interlock admitted individual reads only after a
measured quiet interval on dm-5 and acquisition of the shared Gauss
CPU 2 lock. The run kept nice 15, idle I/O priority, 2 MiB/s pacing,
and one sequential request of at most 1 MiB at a time. Random-access
file advice suppressed sequential readahead. Among logged
observations, full I/O PSI avg10 peaked at **2.17%**, while the
weighted recent device queue peaked at **19.17** and the instantaneous
in-flight count at **39**. The gate repeatedly withheld the read slot
because of device load despite the low global pressure and brief
quiet intervals. At 98.878 s the remaining bytes required at least
29.248 s at the authorized rate with only 21.120 s left. The final
admitted read began with 1.096 s remaining. The existing one-second
cutoff margin prevented another request. The controller clock
starts at staging entry after Python imports and ends after the
final cache check.

After the stop, the existing checkpoint verifier independently hashed
the local 18 MiB extent and matched
`sha256:e5d8e4012d2545db758606414f371177b2a77e2777215d38a4fd500f62b64add`.
It also verified the original manifest and first index hashes without
additional backing reads. The original recording, session, inventory,
and signed window schedule remain bound in the receipt. The partial
extent under `/tmp/leo-v3-0419-first-idle-stage01` is a checkpoint
only. Whole compressed, decoded and per-visit verification are
required for receiver admission. The submitted window authorized no
other waveform member, receiver continuation, solve or new RF.

Staging froze in `219d8e9ba0d0d2a7842ce7e746d34d97b017d064`.
The idle interlock source matched its prior SHA-256 exactly.
[Stage driver](first_member_0419_idle.py) ·
[Component tests](../../../tests/pipeline_eval/test_first_member_0419_idle.py) ·
[Machine receipt](measurements/first-member-0419-idle.json),
SHA-256 `1ce2f2e896c0dfba19cc750937cf9eac06664da036ea5a502be32f4c30113ffd`.
