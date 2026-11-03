# Search and full associations in one scorer session

The private research composition `search_and_associate.cpp` reuses the existing
scorer after the full regional search. It disables objective-only scoring,
recomputes all associations at the selected site and checks that the full
aggregate score equals the search result. The existing search JSON goes to
stdout; the existing full-association JSON goes to a separate, exclusively
created file. Published schemas and normal CLI commands remain unchanged.

The CLI's point renderer is shared to avoid divergent association formats.
Optional progress telemetry records final-association wall time. Failures
return nonzero; an incomplete output file is not a successful checkpoint.

Fresh-track host evidence: all 400 search values match the preceding host run
exactly; all final associations match the saved independent full-score output
exactly (`host-comparison.json`). The component-owned DS9 test additionally
checks all 400 points against the frozen oracle, full associations against a
separate cold score-at invocation, and refuses overwrite of an existing file.
It passes (`component-tests.log`, 107.40 seconds).

The ARM executable links the qualified single-worker 128 MiB PGO scorer library.
`arm-payload.json` pins both hashes. Physical execution completed in 245.042261
wall / 245.016647 CPU seconds, with 120,816 KiB peak RSS. Full final association
scoring inside that run took 1.367468 wall seconds. All 400 search scores and
all associations exactly equal the previously qualified ARM outputs
(`arm-comparison.json`). This is an isolated combined run, not a concurrent
throughput measurement. The earlier queue16 overlap used search-only execution.

Invocation: `search-associate FIXTURE LATITUDE LONGITUDE RADIUS_KM WORKERS ASSOCIATIONS.json`.
The research build uses `LEO_RESEARCH_IMMUTABLE_ORBIT`,
`LEO_RESEARCH_CAPPED_SEARCH`, `LEO_RESEARCH_SCORE_WARM_START`, and optional
`LEO_RESEARCH_SEARCH_PROGRESS`, linked to the qualified location static library.
This prepares the next full-chain overlap to perform final associations on ARM
without parsing coordinates or invoking server-side scoring.
