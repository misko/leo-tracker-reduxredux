# Protected positive/adaptive scanner: exact userspace package

2026-09-09. The updated package cross-builds and passes target loader, protected
saved-IQ SDK/queue/scheduler and owned staging/cleanup checks on the spare ARM
radio. **This is not deployment or live IIO/IRQ/network duty qualification.**
No firmware/FPGA, installed library, production service or new RF collection
was changed or started by these tests.

## What is packaged

The old package predates positive decisions and capture protection. Its passing
checks could not qualify the current implementation. The new candidate combines:

- Existing single-RX amplitude/diversity, energy-support and symbol-support
  numerical variant, one ranked confirmation per 120 ms dwell.
- Positive-only profile, exact score 0.175 and margin 0.025.
- Capture protection: two occupied slots, 250 ms admission age, 500 ms worker
  watchdog, 80% callback budget and four healthy blocks for recovery.
- Adaptive-hop capability; adaptive operation still requires an explicit request.
- Real iiOD, SDK, worker, FFTW, libiio, XML/zlib and both rate-specific templates.

The nine payload files total **3,467,856 bytes**. Each binary's ARM hard-float
ELF dependencies and literal private runtime paths are inspected. No global
`LD_LIBRARY_PATH` override or installed dependency replacement is used. Local
shell fixtures stage, verify and remove the exact eight companion payloads
through 12 real shell operations, without executing ARM code locally.

The release's build/configuration descriptions use new V2 schemas to include
provider-source identity, positive policy, protection and request-only adaptive
capability. Previously published V1 descriptions and wire contracts are unchanged.
These descriptions bind candidate artifacts; they are not qualification certificates.

| Identity | SHA-256 |
| --- | --- |
| Bundle manifest | `7107591248921f22113d2be7cc15ab898325e1b96067eed6bce1deb82fe2efb8` |
| Algorithm build | `b42ad8285aab2ae5d65ca4a532ac27859763161f05973a4530b60da3e7f69f13` |
| Configuration | `b34276d4c9308155a4c78868d2b7807b1612e6a72d18b8f509451759ecc5152a` |

The host candidate now includes current upstream PPU main via local merge
`015b8478`. Its 684 selected bundle/lifecycle/capture/paired-PSS regressions pass.
Leo and libiio already contain current upstream main/master; no upstream commits
were missing when fetched. None of these branches was pushed by this checkpoint.

## Actual target checks

Only exact spare serial `winbond-db620818a328172c` at physical Ethernet
`192.168.1.14` is used, under its shared ownership lock. The current strict SSH
pin, serial/MAC/boot/LAN identity, idle buffers and absence of other clients are
checked before staging, between runs and before cleanup. As in the
[protected 300-second replay](2026_09_09_scanner_protected_arm_checkpoint.md),
USB recovery is not currently attested; CPU-only testing uses current LAN
identity and the historical physical mapping. Firmware `glrt-eth-r60000000-v1`
was already present and remains unchanged.

The real production companion staging/verification/cleanup methods operate on
the exact candidate. `iiod -V` returns before creating an IIO context/listener.
Loader traces prove that it loads the private SDK, libiio, XML and zlib. Traced
saved-IQ replays additionally prove the private SDK and FFTW load paths. The
replay links the packaged SDK unchanged, with the real feedback queue/policy/
scheduler and modeled hardware calls, not a substituted SDK rebuild.

| Per-rate execution | Duration | Results per rate | Unavailable, 2.5 / 5 MS/s |
| --- | ---: | ---: | ---: |
| Loader-traced normal replay | 1.936 s | 16 | 0 / 0 |
| Untraced normal replay | 15 s | 123 | 0 / 0 |
| Forced-pressure replay | 4.840 s | 40 | 11 / 6 |

Across all six runs, **358 results, observations and choices** are accounted for.
All 278 normal checks compute; the two pressure runs compute 63 and emit 17
explicit unavailable records. Computed fractional results agree with the frozen
desktop reference and every choice agrees with the independent policy model.
Pressure recovery and uniform fallback retain the earlier semantics: unknown
is not a miss, admission resumes, capture-long uniform fallback stays latched.

The 15 s untraced worker wall p99/max is **67.97/68.82 ms** at 2.5 MS/s and
**112.86/115.94 ms** at 5 MS/s. SDK callback p99/max is 7.54/8.69 ms and
9.14/13.46 ms respectively. These are short repeated-data package checks, not
another 300 s tail trial or a claim that acquisition/network load fits headroom.
Use the separately documented protected full-duration results for that replay
scope. The actual deployed stack's live capture duty remains unmeasured.

This package reuses the already-opened positive-rich 16-dwell-per-rate stress
packs. It does not replace or mix with the independent
[192-dwell RF quality split](2026_09_09_scanner_rf_dwell_holdout.md). Both preserve
original target identities; neither invents counterfactual adaptive IQ.

## Regression issue, evidence and cleanup

The broad Leo regression initially found 39 failures in one isolated policy-model
fixture: its JSON observation omitted `healthy`, although the C observation had
that field. The protected verifier now reads it to model fallback. The fixture
copies the actual C observation's health; no verifier check, runtime code,
threshold or scientific fixture was weakened. Its focused 48 tests pass. The
complete rerun passes **1,031 selected Leo tests**, and the separate protection
selection passes **147 tests**. The 48 fixture tests and 22 new holdout-accounting
tests are included in the 1,031, not added again. The failed receipt is retained.

All remote companion files, the version-check daemon and three owned replay
payloads are removed through hash/inventory/ownership-checked cleanup. The exact
scratch directory is removed after idle checks. Local original artifacts remain
at `/tmp/leo-protected-bundle.GttGaE/release`. The session-private host credential
copies are removed. No remote scratch, daemon or companion directory remains;
cleanup has no errors, installed hashes are unchanged and the lock is released.

The [evidence index](evidence/2026_09_09_scanner_protected_package/index.json)
retains build settings/source hashes, ELF and loader checks, exact manifests,
all six raw streams and verifications, failed/passing tests and cleanup. The
archive revalidates package bytes, frozen build inputs and every result stream.
Payload binaries, IQ and credentials are excluded.

## Next gate

The package is ready for an explicitly authorized bounded live check, not automatic
production promotion. Compare fixed detector-off/on and then adaptive operation
at each rate, preserving RF bandwidth/IF, valid dwell and guard configuration.
Verify sample-counter duty/continuity, feedback staleness, actual adaptive visits,
recording/UI publication and owned daemon shutdown/restoration. A request for
up to six 300-second captures (30 minutes total RF) on this spare has been sent
to the user; no new RF starts without that authorization.

Remote-main merges and deployment remain open, as does full streaming operational
verification. The implement/test/deploy/verify goal is not complete.
