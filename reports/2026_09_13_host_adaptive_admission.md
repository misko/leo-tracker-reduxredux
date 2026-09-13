# Host-adaptive admission and packaged runtime

The new profile now resolves a V4 intent through normal CLI composition and
dispatches native capture through the existing ownership and iiOD lifecycle.
The database operation key remains the canonical UTC slot across profile changes;
the V4 payload additionally binds profile, mode, detector digest and physical RX.
Retries reuse the exact capture; unpublished evidence prevents another attempt.
The host profile requires one configured radio, a 600-second interval, native
10 MS/s, 300-second runs, 120 ms visits, and a pinned host detector with radio
GLRT disabled. Native capture qualification uses the separate 95% duty floor.

The original qualified host detector binary and seal are packaged unchanged.
Additional release provenance binds `templates.py` and the generated four-frame
template tensor, closing the original provenance gap without altering that seal.
The release manifest digest is
`sha256:09bd961a759bad59d773243a25841a4250f345c6a9c66eb7c0c4afc3e68e1fcf`.
Loading verifies both package files and installed scientific sources/templates.

PPU `df84736033c742c9e405130aad58a14136fc703b` advances the explicitly selected
scanner host runtime to libiio `ab89268c42ae4d2e520e2a0eb1a491e0f459d8dd` and
checks `submit_metadata_feedback`. The default persistent-hop installer pin is
unchanged. The existing `--scanner-glrt` staging option selects this transport;
it does not enable on-radio detection.

The ARM userspace daemon statically links current libiio and the policy SDK.
It has no build-directory RPATH or external libiio/SDK dependency and retains
the same nine system-library dependencies as the working daemon. Its stripped
SHA-256 is `4b56d78be9638126899691804c7fea7daea13acd2ec6b49b9a999304089bb46f`
(300,612 bytes). Build commands and measured provenance accompany the artifact.
Host-adaptive requests disable the daemon's radio detector. Legacy radio GLRT
continues to use its separate companion bundle.

Validation before staging:

- 141 admission, supervisor, lifecycle, capture and release-loader tests passed
  in 6.86 seconds, without RF.
- Nine native provider test executables passed, including adaptive protocol and
  policy tests. PPU runtime/preflight tests passed (23 tests).
- Deployment tests: 340 passed on the first combined run; one new fixture's
  directory-mode setup failed. After correcting that fixture, all six new
  host-bundle deployment tests passed. No validation requirement was relaxed.
- Mypy passed for the three changed runtime Python modules; Ruff and diff checks
  passed for the new Python implementation and tests.

At 19:46 UTC, fixed production scans at 19:30 and 19:40 had succeeded with
954,348 and 954,445 ppm duty. No runtime selector or radio was changed during
this implementation. Staging, saved-data analysis cadence, bounded live canaries,
and the scheduled adaptive cutover still remain. RF budget is unchanged.

Staging caught two packaging defects before any cutover: the host bundle's
pre-seal ownership check needed the extractor's UID/GID, and setuptools omitted
the C/header source files required by the installed detector loader. The former
now has a CLI regression test; the latter is fixed by explicit wheel package
data. A freshly built wheel contains all 27 manifest-bound sources with exact
hashes. Failed unpublished releases were removed by normal staging cleanup.
