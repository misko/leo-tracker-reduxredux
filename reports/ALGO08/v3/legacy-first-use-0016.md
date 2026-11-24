# First DS30-0016 analysis creates all original-file replay maps

One complete analysis of the unchanged original DS30-0016 produced its
ordinary publication and all 13 verified replay maps in **8.038 s elapsed
and 8.027 s CPU**. The earlier same-settings ordinary analysis took
8.630 s elapsed without creating maps. The earlier prepared-map child
took 7.093 s through exit. Its historical preparation and child clocks
sum to 11.993 s. Those reference processes ran separately. The fused
result removes a separate map-preparation waveform pass.

| Original archive and same scientific settings | Raw acquisition elapsed / CPU, s | Process through exit elapsed / CPU, s |
| --- | ---: | ---: |
| Earlier ordinary control | 3.612482 / 3.612193 | 8.629779 / 8.611184 |
| Fused first analysis with all maps | **3.226823 / 3.226646** | **8.037568 / 8.027353** |
| Earlier replay with all maps already prepared | 2.393716 / 2.393584 | 7.092842 / 7.071635 |
| Earlier replay plus historically measured preparation stages | | 11.993402 / 11.971254 |

Fused raw acquisition was 0.386 s faster than the earlier ordinary
control. Through exit it was 0.592 s faster, a 6.9% elapsed difference.
The later decision and publication interval was also 0.252 s shorter.
That latter difference is outside the map adapter. The one new child
does not establish replay-to-replay timing repeatability. Building the
two research libraries and reconstructing the expected custody file cost
0.084301 s elapsed and 0.084284 s combined CPU outside the child. The
earlier portable orbit producer is supplied identically in all three paths.

## Full original verification and reusable output

The fused reader authenticated all **991,734,597** original encoded IQ
bytes and decoded the complete **1,292,800,000** bytes through the
original frame checksums, per-window digests and whole-member digests.
It issued every one of the original **808** rows to the actual receiver,
which retained 95 invalid captures, 93 full two-scan anchors and 620
short visits. The normal bounded input prefetch saw 11 hits in 11
submissions with zero fallbacks. All 242,675 original manifest, index
and payload pages remained resident. The complete child exited 0 with
312 process input blocks and zero major faults.

The same authenticated traversal built five literal maps and eight sparse
exception maps. Each reopened through its existing reader and verified
its first 640,000-byte prefix. Reopening used that member's immutable,
already authenticated encoded snapshot, and no new compressed descriptor
read. All reopened maps regenerated the earlier independent prepared map
bytes exactly. The 2,138,415-byte map collection and 7,902-byte custody
file were published together after both raw acquisition and scientific
publication succeeded. The verified custody SHA-256 is
`ff7b8f4723021bdcde736ef38df9d8199b7efc31082b62d132a18352c1449941`.
Sidecar serialization cost 6.55 ms CPU, reopening cost 49.85 ms CPU,
and final sync and publication cost 2.41 ms CPU. These clocks are inside
the measured child. There were no raw source copies or independent full
waveform replays.

## Exact publication

The original signed native digest
`aeb4658b886daaa4f8a93e99224fb4471f032f91feaa5ce58be2361d7009b4ac`
and native source evidence matched. Both calibration endpoints and RF RMS
values, 115 ordered owners per arm, the original offered region, the
numerical 179-point grid and optimizer path matched exactly. All eight
PNGs matched as encoded and decoded RGBA, preserving the original
recording title. The offline scorer independently checked the grid and
path bindings to the position image.

| Calibration | Latitude | Longitude | RF RMS, Hz |
| --- | ---: | ---: | ---: |
| `c = 0` | 37.845989267 | −122.489763136 | 134.021487 |
| Fitted `c` | 37.847645952 | −122.496772434 | 133.739967 |

Fifteen component and adjacent tests passed. The first setup-only probe
stopped in 0.041 s before importing the sibling launcher under Python
`-I`. It could not open waveform files. The corrected waveform-blocked
probe reached the real scanner, after which exactly one full child ran
at CPU 2, nice 15 and I/O priority 7 under the shared Gauss lock. The
offline verifier uses repository `src` for its read-only workspace API,
while the measured child uses installed storage and numerical science.

Use the [same private read-only mount and CPU lock](legacy-block-raw-0016-protocol.md)
with `legacy_first_map_0016.py launch FRESH_TMPFS_ROOT`. Run its `score`
action after the process exits with repository `src` first on
`PYTHONPATH`. The local complete witness lives at
`/dev/shm/leo-v3-legacy-first-use-0016-result02`.

- [Frozen protocol](legacy-first-use-0016-protocol.md)
- [Final receipt](measurements/legacy-first-use-0016.json.gz), uncompressed
  SHA-256 `5d7355c5288124c039fd373c0aa0c0e555a029882fab0f75acef3c435f6a63e2`
- [Earlier all-member preparation and prepared replay](legacy-block-all-0016.md)
