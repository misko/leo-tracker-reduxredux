# Typed in-memory location session

`native/adaptive/location/session.hpp` introduces a synchronous borrowed-input
port for orbit snapshots and measured tracks. The caller retains immutable
ownership until the call returns, including worker completion. The session
copies only small track descriptors, not orbit states or observation arrays.
It returns owned search/association results and exposes one or two workers plus
an optional caller-thread progress callback. It imports no CLI, filesystem,
storage or network code. The C ABI and persisted JSON/LOC1 formats are unchanged.

The existing CLI now delegates regional search to this port and retains file
loading and JSON formatting. The private scoring engine is shared within the
location component, with internal linkage to keep research build variants
separate. Scorer contexts are RAII-owned; started worker threads are joined on
exceptions. Failed calls leave the caller's previous output unchanged.

Qualification:

- Both complete 400-point host traces (fresh tracks and published memberships)
  are exactly equal to the preceding controls.
- Full fresh-track associations are exactly equal to the host control.
- DS9 composition and one/two-worker score tests pass: 2 tests, 111.18 seconds.
- Component unit checks cover known residual values, serial/parallel agreement,
  immutable input preservation, callback thread/order, invalid worker/input
  rejection, callback failure, and success without requested associations.
- AddressSanitizer/UndefinedBehaviorSanitizer pass for the new session boundary.
- The physical ARM component test passes (0.360 wall seconds, 2,076 KiB RSS).

`comparison.json`, `ds9-tests.log`, `host-build.log`, source snapshots and the ARM
unit receipt are retained. The ARM unit is synthetic; this report does not
claim a new full-catalogue ARM timing or improved concurrent throughput.

The next integration must connect native TLE propagation and the existing
track-conversion port directly to this API, avoiding intermediate orbit/LOC1
files. That complete in-memory pipeline has not yet been deployed or qualified;
the latest full-chain overlap remains the failing file-based trial.
