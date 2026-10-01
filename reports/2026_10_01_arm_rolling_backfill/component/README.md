# Bounded rolling backfill prototype

The v3 prototype is an offline postpass replay over completed forward tracks;
it is not a live bounded-memory API. It preserves the 8-second, 24-state
forward rolling tracker and attaches historical membership without feeding it
back into forward state. Replay identifies the first prefix reaching 8 sources
over 4 seconds as confirmation and exposes only evidence available at that
time. It may inspect the preceding 32-second lane buffer and
walk at most 16 seconds before the forward beginning. Each backward step uses
actual candidate time, alias-aware prediction, an 8-second/32-point weighted
linear fit, the existing 5 kHz maximum gate, a 4-second maximum actual-point
gap, and the existing rate/RMS limits. The implementation greedily retains one
backward association, within the requested maximum of two. Backfill candidates
are restricted to evidence available by confirmation.

Near-identical confirmations with identical candidate, alias, and dealiased
state share a cached historical extension, preventing repeated scans. Cache
membership and source exclusion depend only on the confirmation prefix. Source
groups must span at most 20 ms and are eligible atomically only when every
candidate precedes the forward beginning. The final bank replaces each forward membership with its
backfilled membership where history was accepted; it does not retain an extra
unchanged alternative. Output remains a non-exclusive hypothesis bank.

Component tests cover curved/aliased evidence, crossings, clutter, timestamp
jitter, unattested gaps, noncanonical RF normalization, source-group
atomicity and timestamp bounds, chronological/support/alias output contracts, validation, and a
bounded backfill trigger with added history. Host and ASan/UBSan tests passed,
and the CLI plus unit test cross-compiled for Cortex-A9 hard float. Strict
parsing/evaluation passed on both real frozen inputs. No device or RF action
was performed by this agent.

Final three-run host medians are 0.0713439 seconds for server input and
0.0616309 seconds for ARM input. Backfill raised reviewed representation from the prior rolling
server/ARM 58/39 to 61/47, and recovered refs 12, 48, 51, and 52 on ARM. The
ARM run had 134 unique triggers, 193 deduplicated confirmations, and 3,864
historical point insertions across the full bank, including cache reuses. The
output track count remains 327. Physical ARM
tracking median is 2.55621 seconds and whole-process median is 3.625295514
seconds. Tracking is 128.37% slower than the 1.11931-second rolling baseline,
so the requested <=20% goal is not met.

`arm.tsv`, `server.tsv`, their stderr, and their evaluation JSON files are
copies of the final shared qualification run. `qualification-receipt.json` and
`device-receipt.json` preserve the complete host and physical receipts. Older
`.time.json` and `optimized-arm*` files are provisional development timings
and are not qualification evidence.

Defaults 32/16 and all scientific gates were frozen before these target runs.
No reference labels were used by reconstruction or for parameter selection.
`SHA256SUMS` identifies the frozen source, binaries, tests, and full TSVs.
