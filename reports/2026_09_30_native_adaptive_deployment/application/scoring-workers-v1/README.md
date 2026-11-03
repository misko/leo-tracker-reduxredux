# Shared tracking and scoring workers

Release `3f3c1badd6e740ec` is installed on PLUTO+ `192.168.1.15`. It shares
one bounded analysis pool between tracking publication and satellite scoring,
executed sequentially by the analysis owner. Each scoring lane owns its context
and scratch; fixed satellite partitions reduce in lane order. External execution
bindings cannot be silently replaced by the application's owned pool.

Host and ASAN/UBSAN application lifecycle/CLI tests pass. Full saved-event host
replay with one, two and four workers preserves all 11,747 accepted observations,
64 tracks and exactly equal scores without queue drops. Physical application
unit/CLI tests and one/two-worker replay pass on PLUTO+.

| ARM analysis workers | Publication | Post-producer tail | Whole process | Peak RSS |
|---:|---:|---:|---:|---:|
| 1 | 27.995 s | 52.898 s | 144.349 s | 167,600 KiB |
| 2 | 16.088 s | 34.382 s | 125.691 s | 182,368 KiB |

Both runs replay 299.802 seconds of saved events in approximately 59.964
seconds. Scores are exactly equal between worker counts and within the existing
reference tolerance. The preceding tracking-only release's two-worker tail was
41.019 seconds. These are single runs per configuration, not statistical bounds.

This replay does not run IQ capture or the detector. Two analysis workers occupy
both configured compute lanes; live defaults remain one detector and one
analysis lane. No RF capture or autostart was enabled. Five-second freshness,
strict server equivalence, and physical Pi qualification remain open.

`deployment.json` binds the measurements, executables, online archives and
source snapshot. `source-snapshot.tar.gz` preserves the application composition.
The optional support-profile Session API is present, but the deployed CLI keeps
the portable support path and does not select or link the server math module.

The sanitizer build initially failed when temporary storage filled. Its
successful build used disk-backed compiler scratch and output. The failure log
is preserved separately; it is not counted as a passing run.
