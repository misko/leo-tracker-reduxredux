# One-per-source rank release v1

This release composes the qualified borrowed-string rank comparison into the
current application sources.  The production tracking source is SHA-256
`eeefee63d956a1aeaeb88ee0b2f2560876107a9f5f79e3b5aa28616036d7b96c`.
It differs from the preceding production source only by replacing the two
owning candidate-rank tuples in `one_per_source` with tuples whose numeric
members remain owned and whose candidate identity member is a reference.  The
comparison type, key, ordering, and scientific result are unchanged.

The normal tracking test now exercises the real reconstruction path with two
otherwise identical candidates per source.  The lexically larger identity is
inserted first, the smaller identity wins every equal numeric rank, and reversed
input is bit-exact.  Host and ASAN/UBSAN component builds pass.  All 60 causal
DS9 prefixes serialize exactly like the preceding source, with aggregate
SHA-256 `e9642606acf84a8b4e4817ec082a0381ac51857afb8950cca8ec68cca0014108`.
The production ARM component test also passes; its root-owned receipt is
`../../tracking/one-per-source-rank-production-v1/physical-arm-unit.json`.
The independent lifetime, ordering, and regression review is
`../../tracking/one-per-source-rank-production-v1/independent-review.md`.

The current online library was rebuilt from source for host, sanitizer, and
ARM.  `LEO_ONLINE_BASE_LIBRARY` was unset, and each archive contains the direct
`online`, `tracking`, `pipeline`, `orbit`, `score`, `search`, and `sgp4`
objects.  Thus it embeds the promoted tracking source and the current optional
score cache implementation.  The cache remains disabled by default.  Current
application sources then pass host and ASAN/UBSAN core, CLI lifecycle, and
capability tests; the ARM application cross-build passes.

The complete host saved-event replay accepts 11,747 observations, reconstructs
64 tracks, preserves weighted MSE `64906.771460780015`, and reports zero queue
drops, history evictions, or publication failures.  Its cache budget is zero.
That is a saved projected-event science gate, not a capture-concurrent cadence
qualification; `freshness_qualified` remains false.

Root's earlier CPU-only ARM ABBA over the standalone one-worker tracker measured
26.2540/26.1654 seconds for the control and 24.4408/24.2954 seconds for the
candidate, a 7.03 percent mean reduction.  All four outputs have SHA-256
`6819cb39151bb2cbe894e5d427244aa95d1eae73e17469e5033659d2b0a30084`.
The immutable receipt is
`../../tracking/one-per-source-rank-arm-v1/physical-arm/receipt.json`.  This
does not satisfy the five-second tracking target.

The frozen source closure is under `frozen-closure`; `source-manifest.sha256`
binds its 331 files.  The authoritative projected input has SHA-256
`618fe88156d77b056548b08b49678aa3015ea050d005e26a34aa5ba7d80623de`.
The deployable ARM binary is `build-live-arm/leo-adaptive-live`, SHA-256
`fce5af960f9eba8793140de231cec39a2b1f3c9ae024c91f4d39d763ff8a9c27`,
beside detector DSO SHA-256
`8930f05ef89985df3134ee486fd6cecb3902c79e84e001dc2704fdfd68e678d9`.
No RF or hardware was accessed while producing this application build.

Root subsequently ran the frozen ARM lifecycle tests and deployed this exact
binary as `applications/fce5af960f9eba87`, retaining
`applications/2a01927d03040337`.  The unit test took 0.826036094 seconds and
the CLI lifecycle test took 0.062241025 seconds; both exited zero.  Installed
capabilities match the staged artifact.  `deployment.json` and `physical-arm/`
bind those root-owned results.  Deployment enabled neither RF nor autostart and
does not establish continuous real-time qualification.
