# Full-coverage short stereo receiver on a cold signed prefix

The genuine 12 ms primary with full 20 ms anchors cut native receiver CPU by **52–53%** on the first 192 stereo visits of DS30-0008. From authenticated reader entry through immutable detection readback, it ran in **1.008–1.415 s** against **1.644–1.714 s** installed, a **1.21×–1.63×** paired elapsed improvement. Only the faster candidate rate met both 55-file half-time gates in the more favorable solver scenario. Adding measured worker overhead took its projected aggregate ratio to 0.504. This was a receiver prefix measurement. No whole-recording replay or geographic fix was produced.

The 55-file numbers below preserve the original through-seal transfer. The [durability correction](full-short-seal-scaling.md) uses the reader rate plus one full-size detector seal per recording. The fastest prior reader remains borderline with measured worker overhead, and the slower reader misses both gates.

## Cold measurement

The [protocol](full-short-cold-protocol.md) fixed all 192 visits before measurement. Installed stock used its normal continuation selector. The candidate independently measured both antennas on all visits, using 20 ms two-scan acquisition on the first and every eighth opportunity in each RF, channel and pilot-edge stream. Every other opportunity ran the locally linked true 12 ms signed primary. On full anchors it selected maximum verified margin and broke exact ties by original rank. Its recipe SHA-256 was `13c4ecdb521d02960e61572e8d401a54f165e2c7882112889ede0582abb3ca40`, binding the binaries and callback recipe under a distinct detector and analysis digest.

| Pair and order | Arm | Native CPU s | Complete scoped CPU s | Complete scoped elapsed s | Effective compressed MB/s | Omitted worker elapsed s |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1, first | Installed | 1.008 | 1.483 | 1.714 | 135.39 | 1.912 |
| 1, second | Full-short | 0.483 | 1.044 | 1.415 | 164.05 | 1.842 |
| 2, first | Full-short | 0.475 | 0.957 | 1.008 | 230.15 | 1.881 |
| 2, second | Installed | 1.016 | 1.481 | 1.644 | 141.15 | 1.887 |

All four fresh processes used the same frozen reader, paired decoded SHA-256, compressed buffer and two capped 16 MiB hints. The stock search made 384 full lane calls per run. The candidate made 48 full and 336 short lane calls, with 1.037–1.050 ms CPU per short call across the two repeats. All 192 decoded I/Q digests, timing and probe metadata matched across arms. Both stock repeats reproduced every original published prefix probe. Detection bytes matched exactly within each arm. The timed scope included the same immutable write, fsync and readback path, with 0.006–0.149 s of elapsed for sealing and verification after the reader returned.

All 56,663 payload pages across three copy inodes started nonresident and ended resident on each arm. The authenticated prefix contained 232.084 MB compressed and 307.200 MB decoded. Actual process block reads measured 232.096–232.227 MB, with 0.143 MB written by stock and 0.160 MB written by the candidate. Only the fresh private copy inodes received eviction advice. Their one-time authenticated copy took 4.170 s elapsed and each per-arm eviction took 0.001–0.006 s. These sit outside the scoped clocks. Omitted worker elapsed covers interpreter, imports and other dispatch/exit overhead around the timed scope in this harness. It is used separately as a sensitivity for the historical timing transfer.

## Raw factor survival

Same-visit, same-antenna probe keys were matched one-to-one at two wrapped 10 MS/s timing samples and 250 Hz signed CFO. Each sealed probe had at most one selected factor. Selection was present at 137 of 143 stock-positive lanes, and 122 factors matched the tolerance, 120 with the same original scan rank. The 195 candidate selections included 58 lanes without an installed selection and 15 colocated selections outside tolerance. Twelve of the 58 added lanes were full anchors, where the candidate's selection uses maximum verified margin and stock applies continuation.

| Slot | Stock selections | Candidate selections | Co-located selections | Timing and CFO match | Same-rank match |
| --- | ---: | ---: | ---: | ---: | ---: |
| Full anchor | 13 | 25 | 13 | 13 | 13 |
| Short primary | 130 | 170 | 124 | 109 | 107 |
| All | 143 | 195 | 137 | 122 | 120 |

The 122 matched factors had median absolute changes of 0.324 timing samples and 36.31 Hz, with 95th percentiles of 0.908 samples and 156.81 Hz. Across all 137 colocated choices the 95th percentiles were 1,272 samples and 122.74 kHz. The maximum signed CFO difference in magnitude was 131.00 kHz, so a present factor can represent a substantially different carrier.

The owner rows were read after the four detection files were sealed. Each installed arm had 4,472 owners over the recording, of which 43 belonged to this prefix across three satellite IDs. Both arms had the same prefix result. The candidate returned a factor at 42 of the 43 owner lanes and matched tolerance on 40, including all five anchors, 31 of 33 conditional owner rows, and nine of 10 predictive owner rows. The three misses were one empty predictive lane and two different factors at conditional lanes. These figures score survival of original measured support. They do not assign new owners or establish terminal position accuracy.

## Original timing transfer through the seal

The transfer applies each throughput to the same 55 sealed inventory sizes, retaining the publication tail and scaling each historical solve clock by the stated fraction. The median inventory was 8,235 MB, with one to 106 members across the 55 records. The measured prefix spans just three members of a single recording. The table shows model output in proposed / historical elapsed ratios, with the median individual-file ratio followed by the ratio of total elapsed.

| Solve scaling scenario | Prefix rate and arm | Ratio without omitted worker time | Ratio with omitted worker time |
| --- | --- | ---: | ---: |
| 23.482/60.966 | 135.39 MB/s installed | 0.689 / 0.708 | 0.706 / 0.726 |
| 23.482/60.966 | 141.15 MB/s installed | 0.667 / 0.686 | 0.683 / 0.704 |
| 23.482/60.966 | 164.05 MB/s full-short | 0.595 / 0.614 | 0.611 / 0.631 |
| 23.482/60.966 | 230.15 MB/s full-short | 0.468 / 0.487 | 0.485 / 0.504 |
| 11.680/21.383 | 135.39 MB/s installed | 0.741 / 0.755 | 0.758 / 0.773 |
| 11.680/21.383 | 141.15 MB/s installed | 0.719 / 0.733 | 0.736 / 0.751 |
| 11.680/21.383 | 164.05 MB/s full-short | 0.647 / 0.661 | 0.664 / 0.678 |
| 11.680/21.383 | 230.15 MB/s full-short | 0.520 / 0.534 | 0.537 / 0.551 |

The zero-overhead rates needed to hit the two gates are 209 / 221 MB/s for the first scenario and 245 / 258 MB/s for the second. The faster measured candidate remained below both half-time gates in the 31 historically cold files with measured worker overhead in either scenario. The 12 historically warm files missed both gates even at the faster prefix rate with worker overhead set to zero. The [scored receipt](measurements/full-short-cold.json) preserves all four rate transfers and group thresholds. The large observed run-to-run elapsed spread, full-file member mix and unmeasured geographic evidence limit the transfer to a cost projection.

The [acquisition runner](full_short_cold.py), [post-seal scoring](full_short_score.py), [full receipt with native detection documents](measurements/full-short-cold.json.gz), and [held tests](../../../tests/pipeline_eval/test_full_short_cold.py) reproduce the result. Run the acquisition as a module with the standard sparse-cold Gauss lock and Python path, passing the existing XFS staging root, the pinned short-primary DSO and an unused receipt directory. Then run the scoring module against that directory. Eight focused tests passed.
