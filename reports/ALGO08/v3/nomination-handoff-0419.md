# DS30-0419 nomination-handoff comparison deferred

DS30-0419 was **second of 87** in the unchanged enrollment. Its exact
20 ms detector packet, inventory and original region verified in tmpfs.
The resident catalogue copies failed to reproduce the signed original
catalogue digest. The assignment remains DS30-0419. Neither worker ran,
and the comparison adds no blind speed or accuracy observation.
[Preregistration](nomination-handoff-0419-protocol.md)

| Admission check | DS30-0419 |
| --- | --- |
| Frozen rank hash | `015d6473219fed3585dd3c51586bb9af46f100e7093247d0439538f1f3ef9087` |
| Original odd-ID order | Routed candidate, then installed v3 |
| Historical post-detection boundary | 36.380 wall s |
| Saved-worker estimate under the original rule | **77.759 wall s**, within the 120 s limit |
| Signed recording inventory | 6,774 issued, 5,220 admitted, 14 original segment manifests |
| Original 20 ms detector packet | 4,379,243 bytes, 10,440 radio probes, 4,258 factors |
| Signed original 25 km region | Verified against the archived terminal and release receipt |
| Original causal cutoff | 2026-11-20 06:27:04.637108210 UTC |
| Candidate local catalogue union | 43 snapshot files, 76,890,556 represented bytes |
| Latest snapshot in that union | 2026-11-19 23:01:44.776213741 UTC |

The worker account could inspect 23 catalogue roots under `/dev/shm`
and `/tmp`. A final read-only privileged metadata check covered **84**
catalogue roots across the same two mounts and encountered no permission
errors in the screened paths. It pruned test and source trees, stayed
on each tmpfs device, and refused symlinks. The larger check found
the same 43-snapshot union. Its filename digest was
`sha256:ec1efa4d632f952a27b457b26d98c8d0244ad55a46c743fc17d0b752f721e798`,
compared with the release's required
`sha256:d522aeef3c5da9b482cf58465bf7f8e06d752efc78131605ffc7e883c59a78b6`.
The union used the original 72-hour admission window with the recording
name as the nominal start and the exact signed upper cutoff. That inventory
cannot establish the exact missing-file count. Both censuses record
their scoped inventory. The preflight inspected only local filename
and size metadata for catalogues. It opened no backing archive and
read no catalogue body or waveform bytes.

The candidate runtime was pinned to the unchanged DS30-0255 remediation
source `3a49c5f1241f935d30f3348eed77c8d3c7e4a919`. The only measured
same-input comparison for that build remains its development case,
DS30-0255. The handoff candidate took **56.232 wall / 56.139 CPU s**,
versus **50.721 wall / 50.666 CPU s** for fresh installed v3. Its two
calibrations reproduced **627.115/564.894 m** horizontal error, **111.857/
111.754 Hz** conditional RF RMS and **3,704 ordered owners each**. The
current evidence includes one measured development pair and zero completed
blind pairs for this build. On 0419, preparation and exit clocks, handoff
activation, fixes, both arms' accuracy and RF fits, owners, grid, path
and figures remain unmeasured under the candidate.
[DS30-0255 development evidence](nomination-handoff-0255.md)

The assignment froze in `9b1a5dc605a81a69e2c5e798b8d739029bdb3949`.
Eighteen admission and adjacent handoff tests passed.
[Admission source](nomination_handoff_0419_admission.py) ·
[Tests](../../../tests/pipeline_eval/test_nomination_handoff_0419_admission.py) ·
[Machine receipt](measurements/nomination-handoff-0419-admission.json.gz),
uncompressed SHA-256
`f73374c1223eb6819e62b841cbe8a2a64a9781787afd0624b56c0711d7c2a9b9`.
