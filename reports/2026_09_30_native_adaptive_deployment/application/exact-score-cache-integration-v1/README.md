# Exact score cache application integration

This closure carries the disabled-by-default online exact-score cache through
the saved-candidate `Analysis` replay without enabling it in the production CLI
or changing the portable live v4 JSON contracts.

`Session::exact_score_cache_stats()` is an analysis-owner-only forwarding query.
`Analysis` copies that value into `Summary` after each owner iteration and before
publishing the summary under its existing mutex. Producer-safe `Session::stats()`
remains unchanged and does not read scoring state.

The test-only replay accepts `--exact-score-cache-bytes 0|6291456` as an optional
trailing pair, in either order with `--analysis-workers`. Its output is a new
`leo-paced-analysis-replay/v4` diagnostic shape containing the configured budget,
hits, misses, fallback points, and retained payload. Invalid, duplicate, and
missing option values fail before fixture loading.

The final host cache-off and cache-on runs used all 24,681 projected events,
retained 11,747 observations, reconstructed 64 tracks, and produced exactly
`64906.771460780015` weighted MSE with no queue drop. The cache-on run recorded
405 hits, 240 misses, zero cold fallbacks, one retained site, and 435,752 retained
payload bytes. The runs were concurrent host diagnostics, so their elapsed times
are not a controlled performance comparison.

The ASAN/UBSAN pair at pace 0.05 was also lossless and produced the same score.
It recorded 293 hits, 236 misses, and zero fallbacks in the cache-on run. The
component lifecycle test passes under host, ASAN/UBSAN, and TSAN, including the
owner-to-control-thread summary copy.

Both full-continuous pairs truthfully exit 4: their accelerated producer causes
publication cadence misses, so they are scientific/integration diagnostics and
do not satisfy the five-second continuous freshness gate. The ARM artifact is
cross-built for paired root-owned CPU-only runs. No hardware or RF was used here.

Build roots:

- online: `/var/tmp/leo-online-cache-integration-{host,sanitize,thread,arm}`
- live component: `/var/tmp/leo-live-cache-integration-{host,sanitize,thread,arm}`
- replay: `/var/tmp/leo-paced-cache-integration-{host,sanitize,arm}`

The frozen source copies and manifest are under `source/`; retained JSON and
timing outputs are under `host/` and `sanitize/`.

## Physical ARM comparison

The subsequent root-owned [physical receipt](physical-receipt.json) records one
serial cache-off/cache-on pair on PLUTO+ `192.168.1.15`, at original pace with
two analysis workers and the same binary. Both retain 11,747 observations and
64 tracks, zero drops/evictions/search failures, and exactly the same ARM final
MSE, `64906.771460779819`. Its RMSE differs from the frozen host reference by
only `3.694822225952521e-13` Hz (tolerance `1e-6` Hz).

| Measurement | Cache off | Cache on |
| --- | ---: | ---: |
| Whole-process wall time | 364.280 s | 349.886 s |
| Whole-process CPU time | 583.146 s | 545.279 s |
| Replay wall time | 332.835 s | 318.519 s |
| Post-producer processing | 33.030 s | 18.713 s |
| Serviced / requested cadence | 29 / 59 | 36 / 59 |
| Missed cadence | 30 | 23 |
| Maximum publication computation | 15.471 s | 15.476 s |
| Maximum result source age | 22.522 s | 16.589 s |
| Peak process RSS | 185,444 KiB | 185,708 KiB |

Cache-on records 1,179 hits, 490 misses, zero fallbacks, one retained site and
404,160 retained payload bytes under the 6 MiB budget. The physical component
test passes in 0.850 seconds with 6,924 KiB RSS. Both replay processes correctly
exit **4**, because neither meets five-second freshness. These are fixed-site
saved-event replays, with 299.802 seconds of source evidence, no detector or RF.
Scheduling changes the intermediate prefixes and work count; this single pair
supports an observed improvement, not a repeated statistical speedup claim.
The production cache remains disabled and `live-current` is unchanged.

On the device, from `tests/paced-score-cache-v1`, each run used:

```sh
/mnt/glrtbench/native-adaptive/current/measure-run 600 ./test-paced-analysis \
  ../paced-fit-cache-v1/leo-ingest-ds9.tsv \
  ../paced-fit-cache-v1/ds9-targets.tsv ../paced-fit-cache-v1/tles.txt \
  ../paced-fit-cache-v1/ds9-search.tsv full-continuous 1 \
  --analysis-workers 2 --exact-score-cache-bytes 0
```

The second run changes only the budget to `6291456`. Raw JSON, whole-process
measurements, unit output and device-side input hashes are in `physical-arm/`.
