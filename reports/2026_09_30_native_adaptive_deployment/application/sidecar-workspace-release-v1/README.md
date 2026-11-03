# Sidecar workspace application release v1

This candidate composes the qualified dense source-group sidecar optimization
into the deployed `f51b826eeeebdb23` source closure. The source delta is
limited to `tracking.cpp`, the tracking component build and test, and the
tracking README. The public tracking header, application, online, scanner,
detector, runtime, ingest, timing, and persisted contracts are unchanged.

The optimization binds immutable point indexes to dense lexical source-group
indexes once and reuses lane-local grouping scratch. It preserves lexical
fallback collisions, deterministic ranks and ties, lane isolation, and the
immediate owned copy before nested refinement. Its component qualification is
in [`../../tracking/sidecar-production-v1/receipt.json`](../../tracking/sidecar-production-v1/receipt.json).

`frozen-closure/` contains 309 source and component-test files. The manifest
is `source-manifest.sha256`, SHA-256
`6bccba5a1f2603d680881880a4bc9a43789b03cd47d6c2a3e1e034f6a132f1c0`.
Relative to the prior frozen closure, exactly four files differ: the tracking
implementation, tracking build script, tracking component test, and tracking
README. Online was rebuilt from source, so its archive embeds the sidecar
tracker. The unchanged, previously qualified scanner artifacts are linked by
exact path and hash rather than rebuilt.

Host and ASAN/UBSAN online component builds pass their unit and 492-candidate,
11-track saved-prefix regression. Host and ASAN/UBSAN application lifecycle
tests pass. ARM online, application, and paced-analysis artifacts cross-build.
Host and sanitizer capability JSON is byte-identical to the deployed f51
capability output.

The complete host saved-event replay uses the unchanged v4 harness with two
analysis workers and the exact score cache disabled. It processes 24,681
events, accepts 11,747 observations, reconstructs 64 tracks, and reproduces
weighted MSE `64906.771460780015`. Queue drops, history-capacity evictions,
and publication failures are zero. This coalesced 299.802-second recording is
science and losslessness evidence; it is neither genuine 600-second evidence
nor a five-second freshness qualification.

The ARM deployment candidate is `build-live-arm/leo-adaptive-live`, SHA-256
`bdec8f78923ee41da8f3c357b12bb7635300cb0fb75a9e5dce0b6d7baa3a788a`.
The unchanged detector DSO is
`a62aa336881bbdcfd80fbe61e1fd31fc77aeac643c5fca677414359de00a6deb`.
The ARM paced harness is `build-paced-arm/test-paced-analysis`, SHA-256
`198fe02919a4043007ba934f6b5ae7f3d03d656a2ef8e01f9366ab22b633ba0d`.
Root physically ran both ARM lifecycle suites, verified installed hashes, and
atomically activated `applications/bdec8f78923ee41d`. `test-live` passed in
0.795281804 seconds wall with 6,984 KiB peak RSS; `test-live-cli` passed in
0.062364354 seconds wall with 5,368 KiB peak RSS. The no-argument capability
record is byte-identical to the host record. An initial attempt to use an
unsupported `--capabilities` flag correctly exited 2; the deployed contract
uses no arguments for capability discovery. The prior f51 release remains
installed. No RF was collected and no service or autostart was enabled.

Root also ran the same frozen ARM paced harness twice over saved projected
events. Both executions reproduced 11,747 observations, 64 tracks and weighted
MSE `64906.77146077982`, with zero queue drops, history-capacity evictions or
publication failures. With the exact-score cache disabled, 31 of 59 cadence
requests were serviced, the maximum publication took 13.0572 seconds and the
post-producer drain took 30.9482 seconds. With a 6 MiB cache, 40 of 59 requests
were serviced, the maximum publication took 13.0886 seconds and the drain took
20.7248 seconds. The cache run recorded 1,377 hits and 525 misses while
retaining 404,160 bytes. Both runs failed the five-second freshness gate and
exited 4; the cache remains disabled by default. Result source age is relative
to the latest measured source progress and does not include elapsed wall time
after that progress stops. `physical-paced-pair.json` binds the comparison.
These were physical ARM CPU executions over persisted projected events, with
no IQ replay, detector invocation or RF collection, and the 299.802-second
recording does not exercise genuine 600-second retention.

See `deployment.json` for the lifecycle deployment. Its evidence and the paced
measurements come from root's physical runner and installation tooling.
