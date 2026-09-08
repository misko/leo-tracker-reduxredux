# Scanner GLRT: checked userspace release bundle

2026-09-08. **Local build and portable lifecycle verification, not deployment,
ARM execution of this package, RF collection, or proof of unchanged duty.**

The scanner can now explicitly select a companion manifest through its normal
owned iiOD lifecycle. The lifecycle verifies the actual worker, templates and
libraries before startup, rather than relying only on configured GLRT identity
strings. The locally cross-built candidate contains iiOD plus eight companions,
**3,443,672 bytes total**. All **232 component regression tests pass**.

No production service, installed radio library, FPGA, kernel or flashed firmware
changed. No radio was contacted. No code was pushed, remotely merged or deployed.
The detector remains default-off and its decision policy remains unqualified.

## Implementation

- Leo `328c5f5f9b9c59b4cc6f625b542afe91e89a104f` passes the optional absolute
  `LEO_SCANNER_PERSISTENT_IIOD_BUNDLE_MANIFEST_PATH` through the acquisition
  lifecycle port into PPU. Existing single-binary releases omit it and keep the
  old constructor behavior. It does not itself enable GLRT or change scanner
  dwell, guards, sample rate, bandwidth, IF, block size or scheduling.
- PPU `9dd4b35ce6e83dfa417c4987ded4914f7518ff50` snapshots and hashes all local
  companions before the first remote write. The narrow transport stages them
  in one exclusively created, private, build-specific `/tmp` directory, using
  the daemon session nonce as ownership evidence. Existing pinned SSH,
  exact-serial, port, PID/start-tick and stock-endpoint checks stay in force.
- libiio `a188a70d7f8785b7f342e337655ae537bc20848d` is unchanged in this checkpoint.
  The candidate is rebuilt with its existing GLRT provider, actual artifact
  identities and matching literal runtime paths. Public capture envelopes,
  fractional-counter contracts and V1 daemon lifecycle receipts do not change.

Both IQ streams are still retained; only RX1 is detector input. No hashing,
filesystem publication or cleanup is added to the acquisition callback.

## Startup and rollback guarantees

The manifest declares exact daemon bytes/hash and a bounded list of companions.
Parsing rejects extra/duplicate fields, unsafe or repeated names, invalid sizes
and paths, symlinks, hardlinks, nonregular files, untrusted ownership and
group/other-writable inputs. Reading a FIFO fails instead of blocking. Files
are copied from checked memory snapshots, not reopened during transfer.

The full remote directory inventory, permissions and content hashes are checked
before daemon startup. The private runtime directory is compiled into the
binaries; the implementation does not modify a global loader environment or
replace installed libraries. A manifest is a trusted operator release input,
not a cryptographic signature or a scientific qualification certificate.

Companion cleanup occurs only after the existing lifecycle proves the owned
daemon has exited. It verifies the session nonce, complete inventory, file/link
facts and hashes before removing explicit files and the empty directory. There
is no recursive deletion and no QNAP write. A retry cannot remove dependencies
belonging to an earlier unresolved session; a regression test covers that
failure path.

Missing uploads can be cleaned. Truncated/changed files, unexpected inventory,
an unverified process exit or wrong ownership cause explicit cleanup failure
and retention for inspection. This is **not** reported as successful rollback.
The published V1 stop receipt still lists exactly three daemon files; the
separate bundle manifest records companion identities.

## Candidate package and identity

| Artifact | Bytes |
| --- | ---: |
| iiOD | 195,412 |
| RX1 worker | 75,868 |
| Acquisition SDK | 52,600 |
| FFTW | 932,192 |
| libiio | 138,140 |
| libxml2 + zlib | 1,409,436 |
| 2.5 / 5 MS/s templates | 213,324 / 426,700 |

The worker uses the existing amplitude-ranked, symbol-diverse and conditioned
block-rotation experiment from the preceding replay, not a newly qualified
classifier. Its code/flags and dependencies are recorded by the build helper.
Changing loader paths changes binary hashes; this package still needs its own
target startup and numerical verification.

Algorithm identity is the SHA-256 of canonical content describing the actual
worker, SDK, FFTW and native defines. Configuration identity hashes canonical
RX/rate/dwell/IF/template/confirmation-budget and unqualified-policy settings.
The resulting identities are compiled into iiOD before its own hash is placed
in the bundle manifest, avoiding a circular daemon-hash dependency:

- Algorithm: `10a19ceeb54e1a05f8022a5b8c937f7e596ba7f81315dc62132a8c2a80b5d236`
- Configuration: `f071ba3fa4fedd097091f588439262a2a25616b7c64817741e7d96ee0e0a676d`
- Bundle manifest: `01c6c1b7037a7dd3de700ff78fd7c9e779373f2d2e4d4ee26d26256851407e7b`

These are candidate artifact identities, **not approval for rollout**. The local
payloads remain under `/tmp/leo-glrt-userspace-bundle.CS9kKMOf/release`; no
executable, template payload, IQ or credential is committed to this report.

## Verification and limitations

**147 PPU tests** cover bundle validation, default/opt-in lifecycle, malformed
files, startup/stop failure, previous-session ownership and persistent-hop/raw
capture regressions. **85 Leo tests** cover environment/port composition,
scheduled capture, GLRT metadata, publication, storage and API behavior. Both
suites have zero failures, errors or skips. One Starlette/httpx deprecation
warning is retained; it does not concern this implementation.

Ruff and whitespace checks pass. The two PPU modules pass strict mypy with
imports skipped for the Python 3.11 target and with imports followed under
Python 3.12. The initial normal 3.11-target check could not parse this shared
environment's NumPy stub syntax; no dependency pin or runtime code was changed
to hide that environment limitation.

The actual fixed shell operations are executed in a test-owned local namespace,
substituting only paths and expected uid. An additional run stages all eight
**actual cross-built companion payloads**, verifies every hash, and removes the
test copies and empty directory in 12 operations. Original release files are
retained. This uses no SSH, daemon execution or radio; local shell success does
not establish target BusyBox behavior.

ARM ELF header/dependency inspection verifies hard-float ARM output, that every
non-system dependency is in the bundle, and that daemon/worker/libiio RPATHs
contain only the compiled private runtime directory—not desktop build paths.
System libc, libm, pthread, rt, dl, libgcc and the loader are not replaced or
qualified by this inspection. Target ABI compatibility remains a startup gate.

The [previous 300-second SDK replay](2026_09_08_scanner_glrt_sdk_replay_checkpoint.md)
remains the source of ARM timing evidence. It is not rerun here, and this
checkpoint makes no additional performance, sensitivity or live-duty claim.

## Next gates

1. On an allowed, currently identity/ownership-verified spare, check target
   system-library compatibility and bounded userspace startup/cleanup, then
   verify the exact packaged worker numerically using saved IQ. Do not treat
   a cross-build or version string as full operational verification.
2. Complete detector decision qualification and address the limited 5 MS/s
   worker headroom. Missing or unconfirmed evidence must remain unknown, not
   an absence label.
3. With explicit RF authorization, compare GLRT-off/on 300-second scans at
   both rates under actual IIO/network/interrupt/retune load, preserving all
   acquisition geometry. Check device-counter duty, losses, result inventory,
   source alignment and restoration. Live RF permission is still pending.
4. Review compatible dependency revisions and authorize merge/deployment before
   promotion. The complete realtime-classification/unchanged-duty goal remains
   open until its scientific, operational and delivery requirements are proven.

[Evidence index, receipts, raw test results and recipes](evidence/2026_09_08_scanner_glrt_userspace_bundle/index.json)
retain 28 source/log/manifest artifacts with SHA-256 checks.
