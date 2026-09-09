# Scanner host-runtime release staging

2026-09-09. Local implementation checkpoint, **not deployment or qualification**.
No radio was contacted; no RF, firmware, FPGA, service, data-plane or remote
branch change was made. The prior live results remain in the
[radio18 report](2026_09_09_radio18_live_startup_checkpoint.md).

## Gap and implementation

The installed canary host successfully uses PPU's explicit GLRT-capable ABI-3
runtime, but release staging always requested the original ABI-3 native source,
and publication inventory validation rejected the new source. A deployed
scanner cannot rely on a development venv or a private library override.

The raw release stager now forwards `--scanner-glrt` **only when explicitly
requested**. The release-metadata validator recognizes exactly two frozen host
identities, not arbitrary ABI-3 binaries:

| Host runtime | Exact libiio source | Fresh staging selection |
| --- | --- | --- |
| Original persistent-hop | `f6c450eada95ce99fe8756ebc244bfcf6ddcc72a` | Unchanged default |
| GLRT-capable | `a1088b61de3c57762cfed5533e1baf8076a7b726` | Explicit `--scanner-glrt` |

This is the **host transport**, not the ARM provider revision `4323b93` used
in the latest live canaries. The original static ARM daemon, its provenance
checks, and acquisition enablement remain unchanged. Host capabilities alone
cannot enable GLRT or replace the required companion bundle.

PPU's existing immutable source-bound receipt already identifies the selection;
no new persisted schema, profile file or digest-layout change was introduced.
Exact source selection, receipt/library/binding hashes, release-local paths,
ownership/modes and isolated fresh-process validation remain mandatory.
An explicit scanner request rejects an already-staged legacy runtime. With no
explicit request an existing release is simply revalidated, never rewritten.

## Tests and actual installed-runtime verification

- Five new focused tests failed against the original validator, then passed.
- **238 deployment tests pass**, including legacy metadata, new exact identity,
  arbitrary-source rejection, native tampering and receipt relabeling,
  requested-profile mismatch, actual shell argument forwarding, and complete
  non-mutating dry-runs for both selections. Existing ops/cutover, rollback,
  publication and systemd tests are included; none accessed radio hardware.
- Ruff lint/format and Bash syntax checks pass. Early unused-import/formatting
  issues were corrected; no validation expectation or scientific fixture was
  weakened to get a pass.
- The actual installed canary venv passes the new inventory selection and the
  existing isolated published-release native verifier. Cancel/status/drain
  methods are present with the expected signatures. Native SHA-256 remains
  `a09b77cf0c0101204163abae8c90a6abc170199ee61836c5133dc3194569df3e`;
  binding SHA-256 remains
  `5ed5cb596f24ceeb857b27eefe5303eeb4f1e9ed2c1f2a31a2ca5746d8fa52bb`.
  This verifies installed host loading, **not a newly root-sealed production
  release, full staging execution, or another RF run**.

Remote bases were refreshed read-only. Leo still contains remote main
`29be8492f5f2efb439a9df1e6086224714e95506`; libiio still contains remote master
`c752ab684a4c9924ee362ccfb02a7ac65f7992f9`. PPU gained one independent,
hardware-free RX-interface-evidence change. It was reviewed and merged locally
at `6b577ac229fe4b7b43528ff469dd197f9550e268`, incorporating remote main
`4bc2ca6a50dd8dd3c925522acfff5466385fbfd5`; its **72 new component tests pass**.
No scanner code changed in that reconciliation. The previously executed
canary venv was not rebuilt or relabeled as this newer PPU package.

## Remaining release gates

The committed Leo lock still pins PPU `7210cda9...`, whose installer does not
support `--scanner-glrt`. The newer host/native changes are still local rather
than integrated into the respective fetched remote main/master branches.
Therefore the new staging option is **not yet a claim that a complete scanner
release builds from the current frozen dependency lock**. Unsupported dependency
options or wrong native identities must fail, not fall back silently.

Next integrate the exact reviewed dependencies and lock, package/seal the ARM
companion bundle, and exercise a full isolated release build. Preserve the
original fixed scanner and default-off flags. Production promotion still needs
the remaining quality/duty/positive-signal adaptive gates and deployed UI,
rollback and operational checks. At 5 MS/s, measured confirmed CPU p99 remains
about 194 ms and live screening coverage 26.63%; this staging work does not
improve those measurements. More full-length RF tests require new authority.

[Evidence index](evidence/2026_09_09_scanner_release_runtime/index.json) retains
the failing/passing test receipts, real installed-runtime verification recipe
and result, exact changed files, and dependency reconciliation identities.
