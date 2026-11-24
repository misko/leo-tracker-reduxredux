# Direct packed North capture and first publication

The direct packed route took **13.580 s** from the writer's first input through authenticated analysis, both calibration fits, eight figures and exit. The independent ordinary capture followed by installed ALGO08v3 took **19.529 s**. This is **1.438×** on one matched resident North simulation. It falls 1.374 s short of 1.6× and 3.816 s short of 2× at the measured control time. [Frozen protocol](north-direct-multichunk-protocol.md) · [Receipt](measurements/north-direct-multichunk.json.gz)

| Measured boundary | Ordinary v2 Zstandard source + installed v3 | Private packed CI16 source + adaptive 20/8 |
| --- | ---: | ---: |
| Capture to durable files and own authority, wall / CPU | 2.825 / 2.823 s | 2.543 / 2.542 s |
| Fresh publication process through exit, wall / CPU | 16.704 / 16.461 s | 11.037 / 10.960 s |
| Complete writer through exit, wall / CPU | 19.529 / 19.292 s | 13.580 / 13.507 s |
| Emitted recording bytes including indexes and manifests | 1,580,164,182 | 1,587,127,445 |

The new writer saved 0.282 s. The remaining 5.667 s difference is the combined reader, detector, solver and publication comparison. The two routes use different receiver and solver recipes. The ratio for the analysis children alone is 1.513×. The packed child's authenticated acquisition took 5.480 s including 304 full and 2,096 short native lane calls. Full decode and decoded integrity checks inside that boundary took 2.110 s wall and 2.108 s CPU. The installed child uses its standard authenticated reader. This run did not instrument isolated reader or decoder time inside that child.

## Custody and timing scope

Before either clock, the same pinned original 19-member North simulation was checked for tmpfs residency and hydrated once into 1,200 immutable owned stereo windows. The authenticated hydration took 4.445 s and provided 1,920,000,000 decoded bytes, with no input blocks or major faults. It models already-owned samples and is outside the prospective capture clocks. The pinned codec was built and a shared font cache prepared before timing. The measured ordinary writer paid nine process major faults and 384 input blocks with no original waveform reads. The packed writer paid zero of either. Results are from one ordinary-then-packed order under the shared low-priority CPU 2 lease.

The ordinary writer emitted its own installed-format manifest. The private writer committed its own typed root, independently bound all 19 ordered index and raw-member digests, and wrote a hash for each exact encoded part and its decoded bytes. It used no original or ordinary compressed digests as authority. The private reader authenticated all 2,400 encoded blocks and all 1,200 complete windows, then confirmed all 19 whole decoded member digests while feeding the actual native receiver. The installed child's independently read inventory and signed packet were checked against the ordinary producer's manifest pin and all original window hashes after exit. The packed child's own root pin was passed explicitly to its private reader. Both writer outputs held the original ordered index content and raw-member digests. The fresh capture identities produced different session, run and owner hashes from prior analyses. The causal archive and cutoff, containing offer and simulation RF metadata all matched.

The 64-window functional smoke authenticated 84,400,256 packed payload bytes and 102,400,000 decoded bytes, with both encoded frames per window checked. The 20/8 detector returned the same ordered signed factors as the ordinary reader after excluding only capture-bound identifiers. Tests cover full multichunk readback, corrupt encoded tails, chronology, root mismatch and physical owner mapping. The experiment only admits complete dual-antenna, 200,000-sample windows. It provides no transfer evidence for invalid or shorter physical extents.

## Scientific output

| Evidence | Installed c = 0 | Installed fitted c | Packed c = 0 | Packed fitted c |
| --- | ---: | ---: | ---: | ---: |
| Position error | 105.690 m | 140.779 m | 111.954 m | 128.086 m |
| Conditional RF RMS | 5.406 Hz | 5.167 Hz | 9.133 Hz | 8.921 Hz |
| All-owned figure RF RMS | 9.697 Hz | 18.570 Hz | 44.983 Hz | 50.415 Hz |
| Owned observations | 302 | 302 | 342 | 342 |

Both arms on each route matched the exact location, RF values, path and map against their own independently verified North reference. The installed route retained 137 grid locations. The packed route retained its 78 adaptive samples, the same phase state and exact ordered physical ownership and roles in both calibration arms. Owners were joined through the original receiver, channel, visit and signed sample counter, with the published session-derived digests checked before remapping. The installed output exposes digests and counts rather than ordered owner rows. Its fit, owner counts, track and satellite totals, map, path and plot content match the prior named reference. Each route produced eight digest-checked and decoded PNGs with the original dimensions. The only pixel changes were confined to the recording-name title line, now displaying the new capture basename. The reader verified each new figure against its own run-bound manifest. [Prior adaptive and named references](adaptive-raw-map.md)

## Reproduction

The timed source is `c38ea5994`, based on `00bb614b7` with the one-member custody gate `e43448cbe`. Use a fresh absolute `/dev/shm` output, the installed v3 Python and pinned resident North fixture. Set local `PYTHONPATH` to the repository, its `reports/ALGO08/v3` directory and installed v3 release `src` and root. Set single-thread numerical environment and run `python -Bm reports.ALGO08.v3.north_direct_multichunk smoke /dev/shm/<fresh-root>` and then `run` with a different fresh path under the Gauss CPU 2 lock. The scored full invocation and exact original option vector are in the receipt. Run `python -Bm reports.ALGO08.v3.north_direct_multichunk_score <result-root> <fresh-score.json>` after the processes stop. The adapter and its temporary port are confined to the research harness.
