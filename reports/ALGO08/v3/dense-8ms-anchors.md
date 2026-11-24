# Dense signed member with 8 ms primaries and first-scan anchors

Using 8 ms short primaries saved **21.087 and 16.169 CPU ms** in the two reversed comparisons of complete authenticated member acquisition. Replacing its 20 ms two-scan anchors with verified native first scans saved another **8.350 and 20.802 CPU ms**. All 128 emitted 8 ms probe rows matched across the two anchor modes. Whole fresh process clocks varied with setup and exit costs. The experiment measures one signed member, using six fresh processes. [Frozen protocol](dense-8ms-anchors-protocol.md) · [Verified timings and signed rows](measurements/dense-8ms-anchors.json.gz)

## Receiver and authenticated member clocks

All arms independently read and verified the same **77,442,779 compressed bytes** plus the original index and manifest. The released reader produced **102,400,000 bytes** of signed stereo samples. Both radios paid for every one of the 64 issued visits, with **16 full-anchor and 112 short** lane calls. The 18,952 source pages were resident around every fresh child. The same signed buffer, index checks, paired native per-window and whole-member hashes, clock and coverage checks ran on all six traversals. The ordered original 64 I/Q hashes matched the archived prefix. Only the original first member on tmpfs was in scope. [Previous live first-member acquisition](live_stereo_0008.py)

| Order within paired round | Full / short receiver | Anchor / short native CPU, ms | Verified member acquisition CPU / wall, ms | Whole fresh process CPU / wall, s |
| --- | --- | ---: | ---: | ---: |
| 1A | 20 ms two scans / 12 ms | 43.375 / 113.235 | 293.584 / 296.687 | 1.779436 / 1.784560 |
| 1B | 20 ms two scans / 8 ms | 43.649 / 91.172 | 272.496 / 272.503 | 1.739865 / 1.741234 |
| 1C | 20 ms first scan / 8 ms | 28.930 / 94.803 | 264.146 / 264.152 | 1.812524 / 1.813944 |
| 2C | 20 ms first scan / 8 ms | 29.758 / 95.229 | 266.989 / 266.995 | 1.831838 / 1.833758 |
| 2B | 20 ms two scans / 8 ms | 48.307 / 96.953 | 287.792 / 287.798 | 1.845607 / 1.847100 |
| 2A | 20 ms two scans / 12 ms | 44.772 / 118.558 | 303.961 / 303.973 | 1.844750 / 1.846233 |

The member clock includes native context setup and cleanup, decode and validation of all original signed samples, the original callbacks and projection of the probe digest. Outside the callbacks, read, decode and validation in the member iteration took **130.60–134.96 CPU ms**. Native context setup took **4.33–4.76 ms** and cleanup **0.28–0.36 ms**. Input and installed source bindings took **386–454 CPU ms** in the fresh worker before the member clock. Those checks, output seal and readback at **0.64–0.69 ms**, imports and cleanup through process exit are charged in the wider clock. The first 12 ms process recorded 688 input blocks and nine major faults. The other five reported zero of either despite comparable source residency. The counters are process-wide and leave the fault source unassigned. The 8 ms two-scan build saved 43.33 ms in the first fresh process comparison and cost 0.87 ms more in reverse. The first-scan build's verified acquisition saved 29.44 and 36.97 CPU ms against 12 ms. Its wider exit comparison changed sign as well.

## Signed observations before any held selection

The 12 ms control reproduced all 128 original frozen prefix probe rows. The 8 ms two-scan control independently matched all 128 rows from the earlier authenticated 8 ms archive. Both had nine verified full-anchor factors. Moving to 8 ms changed short selection from **58 to 61**. Eight previously positive lanes had no new selection and eleven gained one. Fifty paid short lanes had a factor in both builds with changed signed values, of which 41 matched within **two wrapped samples and 250 Hz**. Across those 50 shared short lanes, median absolute differences were 0.261 samples and 56.840 Hz. The largest were 3,383.868 wrapped samples and 212.858 kHz. [Prior full-aperture and short archive](eight-ms-primary.md)

The 20 ms first-scan path used the separate verified `primary_factors` helper and original installed receiver context on the actual IQ. Its distinct recipe certificate includes the helper DSO and source digests. It independently reproduced B’s nine full-anchor factors and seven empty anchor lanes. The previously measured native two-scan/first-scan ledger agrees at each of these same anchor positions. All 112 short probe rows also matched exactly. The older native ledger records a different winning anchor at visit 71, outside this member. All six fresh processes recorded zero CFO tails and zero held selection calls, and neither 8 ms arm uses a 12 ms factor. [Upstream first-scan adapter](primary_anchor_8ms.py) · [Older signed anchor ledger](measurements/anchor-primary-dense-prefix.json)

The original 20/12 ms schedule here matches the recipe behind the earlier **32.403 CPU s** complete dense acquisition. The six measurements cover the member read and its first signed detector output. No position, receiver-history route, full recording or full dense raw-to-exit time was measured. [Earlier whole recording boundary](dense-full-short-raw.md)

Run `dense_8ms_anchors.py launch FRESH_TMPFS_ROOT` and `score ROOT` from freeze `82dccfab8` as the original staged fixture owner, with the shared Gauss lock, CPU 2, nice 15, I/O priority 7 and one numerical thread. The saved comparison verifies the deployed library and the unchanged first-scan adapter from `cb7772425`. Thirty-three focused tests passed. [Receiver comparison](dense_8ms_anchors.py) · [Owned tests](../../../tests/pipeline_eval/test_dense_8ms_anchors.py)
