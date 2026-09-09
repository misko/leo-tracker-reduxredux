# Scanner companion release packaging

2026-09-09. Local implementation and tests; **not remote promotion, deployment
or new RF qualification**. No radio, SSH connection, ARM binary, firmware
operation or production service was used in this checkpoint.

## Delivered

`runtime/scanner-glrt` now carries the exact nine payloads and three manifests
from the successful source-pressure canaries, with no recompilation or byte
changes. The old `runtime/scanner-iiod` and its strict provenance remain intact.
Host runtime selection, ARM bundle selection and scanner enablement are
independent; adding an asset to a release does not enable scanning.

The optional bundle validator checks the three frozen manifest identities,
every payload's digest/size and ARM hard-float EABI5 identity, trusted ownership
and modes, exact inventory, and rejection of links, FIFOs, oversized or
group-writable inputs. Paths are fixed reviewed names, not arbitrary paths from
untrusted metadata. The bounded file reads detect input changes and do not
follow final file symlinks. QNAP and symlinked directory paths are rejected.

Release staging verifies before normalizing the enumerated files, then sets
iiOD/worker to 0550 and the other files to 0440. The published-release and
external-metadata validators both check the candidate. All 12 paths enter the
external sealed inventory; old releases without the optional asset still use
their original inventory. The raw stager also preserves older committed
sources that lack the optional directory/helper. Ops maps bundle changes to
acquisition impact and both acquisition/deployment test gates.

The build's private runtime directory is embedded in native artifacts. This
step provides **byte-preserving packaging**, not a bit-reproducible compiler
build. A fresh namespace/build changes identity and must be requalified.
See [asset provenance and notices](../docs/dependencies/scanner-glrt-runtime.md).

## Verification

- **282 deployment tests pass**, including 62 focused asset/metadata tests.
  These runs overlap and must not be summed. Tests use the actual candidate
  bytes without executing them, exercise mutation of every file, missing and
  extra entries, hardlinks, symlinks, FIFO/oversize/mode failures, exact external
  sealing, and legacy absent-bundle behavior. Rehashing external metadata cannot
  authorize a changed candidate because its reviewed manifests are also pinned.
- The packaged 12 files compare byte-for-byte with the original canary bundle.
  Current source files still match **29 worker, 14 SDK and 175 provider**
  build-input hashes. These counts overlap headers and are not independent
  scientific tests. Provider source remains committed, clean `4323b93...`.
- A separate Git-object export contains all 12 assets and passes the exported
  validator with unchanged bytes. This caught the global `*.so` ignore rule:
  only the reviewed SDK now has an explicit tracking exception. It also exposed
  archive permissions that can be group-writable. The stager now explicitly
  sets `git -c tar.umask=0027 archive`; a real GNU-tar regression rejects an
  unmasked export and passes the corrected one, even with conflicting local
  Git configuration. Trust checks were not relaxed. This export is not a full
  dependency install/web build or root-sealed production release.
- The public PPU bundle loader accepts the packaged manifests. Its real
  companion stage/verify/cleanup shell operations were exercised through a
  **local runner**, substituting only a test filesystem namespace and expected
  local uid. All eight companions (3,257,300 bytes) were copied exactly. A
  modified worker caused cleanup to refuse; after restoring the original
  bytes/mode, cleanup passed and removed only the owned namespace. An unrelated
  sentinel survived. There were 15 local shell calls and no SSH subprocess.
- The initial local harness used a documentation-only IP literal, which PPU
  correctly rejected before staging because its public contract requires
  `192.168.1.*`. The corrected fixture retains that contract shape and the
  injected local-only runner. No host validator was relaxed and no address
  was contacted. It is not a new BusyBox/ARM or process-exit qualification.
- Ruff lint, targeted formatting and Bash syntax checks pass. The tested
  numerical settings, thresholds, native code and scientific fixtures did not
  change. Third-party notices are retained alongside the deployment docs.

## Evidence and remaining gates

The bundle identity remains
`19c3650480a8386b12384b0f9a0c5d49e237b04ad98f474d3e703d3f820ddd7c`, algorithm
`3a2b6f66a39f197f8544be8a7af635122d762fc3bf2c649ee4c8937d1490b41c`, configuration
`7119b7116309835f308c5db23acb23b0e98f098fdf4c853caf8e4f0bb83424f8`.
[Evidence index](evidence/2026_09_09_scanner_bundle_release/index.json) retains
test receipts, source audit and recipes, original SDK/worker build receipts and
the local companion-operation result. Dummy credential files are not archived.
The [export follow-up](evidence/2026_09_09_scanner_bundle_release/export-followup.json)
separately retains the permission correction, final 282-test receipt and
[successful Git-object export](evidence/2026_09_09_scanner_bundle_release/git-export.json),
without overwriting the initial snapshot.

The locked PPU revision still predates the GLRT installer/companion capability,
so this is not a successful full frozen-dependency release build. Exact
dependency promotion/pins and an isolated end-to-end stage remain next.
No new claim is made about detector sensitivity, 5 MS/s every-dwell performance,
unchanged duty, positive-signal adaptive weighting/cooldown, deployed UI or
rollback. The [live report](2026_09_09_radio18_live_startup_checkpoint.md) retains
the measured 94.47%/94.16% duty and 26.63%/100% screening results and the failed
comparison attempts. Additional full-length RF requires new authority.
