# Isolated endpoint-bank capacity comparison

One worker with a 128 MiB endpoint-bank limit saves 8.647% CPU against the same
ordinary vector scorer with its default 64 MiB limit on 16 held-out sites.
ABBA mean CPU: 11.983628 seconds (64 MiB), 10.947392 seconds (128 MiB).
Peak process RSS increases from about 94,596 to 116,912 KiB. Every ARM score
matches the qualified control exactly. The full 400-point host search also
matches the preceding host result exactly. This is not a full ARM throughput
measurement and does not qualify continuous cadence.

The bank size is a private research compile option; defaults remain unchanged.
`build_heldout_bound.sh` accepts default/32/64/128 MiB as argument 16.
`bench_search_sites` now accepts optional worker count 1 or 2 (default 2).
The ARM sequence is 64/128/128/64 MiB with one worker throughout, using pinned
binaries in `protocol.json`. Inputs are recorded with their device hashes.
The endpoint-bank unit test passes on ARM; all eight host research units pass.
A separate host compile with a one-block default verifies that the override
obeys the bounded-capacity fallback rather than silently allocating more.

The result supports cache capacity as a contributor to the earlier one-worker
slowdown. It does not isolate or eliminate memory-bandwidth contention during
GLRT overlap. A fresh profile and full concurrent replay are required next.
