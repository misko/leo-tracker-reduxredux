# Publication stage profile

This test-only profiler measures one saved-event application replay without
changing production code or schemas. GNU linker wrappers bracket the existing
`Session::publish`, `Coordinator::publish`, `tracking::reconstruct`, and
`pipeline::make_location_tracks` calls. The intervals isolate:

- candidate and graph materialization from Coordinator entry to reconstruction;
- reconstruction itself;
- the capacity-check gap before location conversion;
- `make_location_tracks`;
- snapshot allocation, moves, commit, and local candidate/graph/track cleanup
  performed before Coordinator return; and
- the remaining outer Session wrapper.

The wrappers use the ABI-correct Coordinator symbol on each target: `long` (`l`)
on x86-64 and `long long` (`x`) on ARM32. Every successful row must have complete
stage timestamps, and its stage partition must exactly equal both Coordinator
and Session wall durations. A fixed 128-row table avoids allocations in the
timing path.

The full host coalesced replay retained all 11,747 observations, reconstructed
64 tracks, and produced weighted MSE `64906.771460780015`. The full publication
took 501.135 ms:

| Stage | Host time |
|---|---:|
| Candidate/graph materialization | 13.659 ms |
| Tracking reconstruction | 467.489 ms |
| Tracking-to-location check | 0.001 ms |
| Location-track construction | 14.452 ms |
| Snapshot pack/commit/local cleanup | 5.533 ms |
| Outer Session wrapper | 0.001 ms |

Host evidence is a correctness and instrumentation check, not an ARM performance
claim. The subsequent [physical ARM receipt](physical-receipt.json) records a
lossless full-coalesced replay at pace 0.2 with two analysis workers, bounded to
600 seconds. The first attempt at pace 0.01 dropped two events and exited 4;
its complete raw evidence remains in `physical-arm/rejected-100x`. It is not a
full-data qualifier. The profile does not execute IQ, a detector, or RF.

The successful ARM replay retained all 11,747 observations and 64 tracks, with
zero drops and final MSE `64906.771460779819`, within the reference tolerance.
It published once initially with six observations and once at the full input.
All stage partitions are complete and sum exactly to the enclosing durations.
The full publication took **15.333 seconds**, of which **14.761 seconds (96.3%)**
were tracking reconstruction. Materialization took 0.113 seconds, location
conversion 0.418 seconds, and snapshot/cleanup 0.041 seconds. All nontracking
publication work together took only 0.572 seconds. Packaging optimization alone
cannot close the five-second publication gap. Whole-process time was 124.948
seconds, CPU 95.007 seconds, RSS 182,476 KiB, and exit status 0. This coalesced
stage-isolation pass does not qualify continuous freshness.

Builds:

```sh
LEO_ONLINE_LIBRARY=/var/tmp/leo-online-cache-integration-host \
  bash tests/native_adaptive/application/research/build_publication_profile.sh \
  host /var/tmp/leo-publication-profile-host
LEO_ONLINE_LIBRARY=/var/tmp/leo-online-cache-integration-arm \
  bash tests/native_adaptive/application/research/build_publication_profile.sh \
  arm /var/tmp/leo-publication-profile-arm
```

Run:

```sh
LEO_PUBLICATION_PROFILE_PATH=profile.jsonl ./test-publication-profile \
  PROJECTION TARGETS TLES SEARCH full-coalesced 0.2 \
  --analysis-workers 2 --exact-score-cache-bytes 0
```
