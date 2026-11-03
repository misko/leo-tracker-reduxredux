# Source-key view application release v1

This release composes the promoted tracking source-key view optimization into a
coherent build of the current native application. The tracking source is
SHA-256 `b56a93a22fb9923b6b7dc24d43fd982cb722bd1dafd2e432d802c914f61d326d`
and is byte-identical to the independently reviewed research source. The
optimization changes ownership of temporary source-group map keys only; the
tracking algorithm, public contracts, and serialized science are unchanged.

Relative to the preceding `one-per-source-rank-release-v1` closure, current
source also contains the additive single-receiver detector/scanner interface,
the USB source-port adapter, and the server-reference geometry safety guard.
The deployed local-PLUTO application still selects the dual-receiver scanner;
the single-receiver and USB paths are not selected by this binary. The ordinary
detector DSO includes the additive single-receiver ABI. The server-reference
geometry guard belongs to the separate research detector profile and is not a
claim that wideband reference mode is supported by this application.

The frozen closure contains 309 source and component-test files. Its manifest
is `source-manifest.sha256`, SHA-256
`f532b842ca895ff484bee05e91607dcd2adc128cc941f89ba33b0978809b44a8`.
Online was rebuilt from this closure without a base archive, so its archive
directly embeds the promoted tracker. Host, ASAN/UBSAN, and ARM online builds
pass; the online-owned saved fixture is a 492-candidate, 11-track prefix
regression rather than a complete-corpus test.

Scanner host and ASAN/UBSAN component tests, the dual-receiver saved-IQ test,
and the new single-receiver saved-IQ test pass; ARM cross-build passes. The
shared host `/tmp` quota was exhausted, and glibc `tmpfile()` ignores `TMPDIR`,
so a report-local `tmpfile_redirect.c` interposer sent test-only temporary files
to `/var/tmp`. It is not part of any archive, application binary, or deployment.
The initial quota failure and the first sanitizer preload leak report are
preserved. Sanitizer tests were rerun directly with leak checking enabled and
empty stderr.

Application host and ASAN/UBSAN core/lifecycle tests pass, and the ARM
application cross-build passes. A complete host saved-event replay processes
24,681 events, accepts 11,747 observations, reconstructs all 64 tracks, reports
weighted MSE `64906.771460780015`, and has zero queue drops, history evictions,
or publication failures. The exact score cache remains disabled by default.
This coalesced recorded replay is a science and losslessness check; it is not a
continuous five-second freshness qualification.

The ARM deployment candidate is `build-live-arm/leo-adaptive-live`, SHA-256
`f51b826eeeebdb23c68c4aa065680a39d974e3d8035d29197041d0e17ed46630`,
with detector DSO SHA-256
`a62aa336881bbdcfd80fbe61e1fd31fc77aeac643c5fca677414359de00a6deb`.
Root ran the exact ARM lifecycle artifacts on the PLUTO CPU and activated them
as `applications/f51b826eeeebdb23`; `live-current` resolves to that directory.
The core test took 0.832327466 seconds and the CLI lifecycle test took
0.063165475 seconds, both exiting zero. Installed binary and detector hashes
match the staged artifacts, and installed capabilities are byte-identical to
the host capability receipt. The previous `applications/fce5af960f9eba87`
release remains present. Deployment enabled neither RF nor autostart and does
not establish continuous real-time qualification. `deployment.json` binds the
root-owned physical and activation evidence.
