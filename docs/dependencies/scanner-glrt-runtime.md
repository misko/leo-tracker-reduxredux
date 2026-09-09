# Optional scanner GLRT ARM companion asset

`runtime/scanner-glrt` preserves the exact userspace bundle exercised by the
September 9 radio18 source-pressure canaries. It is separate from the unchanged
default `runtime/scanner-iiod` asset. Presence in a release does not enable it,
change firmware, authorize RF, or establish detector/duty qualification.

| Identity | SHA-256 |
| --- | --- |
| Bundle manifest | `19c3650480a8386b12384b0f9a0c5d49e237b04ad98f474d3e703d3f820ddd7c` |
| Algorithm/build | `3a2b6f66a39f197f8544be8a7af635122d762fc3bf2c649ee4c8937d1490b41c` |
| Configuration | `7119b7116309835f308c5db23acb23b0e98f098fdf4c853caf8e4f0bb83424f8` |

The nine payloads total 3,467,936 bytes: iiOD, one numerical worker, the SDK,
private libiio/FFTW/libxml2/zlib shared libraries, and two rate-specific pilot
template files. Three identity manifests bring the inventory to 12 files.
Do not add arbitrary files to this exact bundle directory. Deployment verifies
all manifests, payload digests, sizes, ARM hard-float EABI5 headers, modes and
ownership. It rejects missing, extra, linked or group-writable inputs. Every
file joins the release's external immutable digest inventory; older releases
without this optional directory retain their original inventory.

The provider source is libiio `4323b93a17ff2a0e8954fc5ffd9367a40540bebe`.
The host transport separately requires PPU's explicit ABI-3 GLRT runtime at
libiio `a1088b61de3c57762cfed5533e1baf8076a7b726`; these revisions serve
different roles. The locked PPU revision must be promoted before the full
scanner release path is ready. All these changes remain opt-in.

The daemon and worker embed the bundle's private `/tmp/ppu-iiod-bundle-*`
runtime directory. PPU stages and verifies companions there under its owned
userspace lifecycle, then removes only its verified enumerated files after
process exit. No global loader environment or installed radio library is
replaced. System glibc/libm/libpthread/libdl/librt/libgcc and the ARM loader are
not bundled; target compatibility is a separate qualification condition.

This is **byte-preserving packaging**, not a claim of bit-reproducible
cross-compilation. The original research builder generates a runtime namespace,
which changes embedded paths on a fresh build. Preserve these artifacts and
receipts; a changed build must have new identities and matching verification,
not an inherited pass by filename.

Build recipes, SDK/worker compiler and source hashes, provider inputs, dynamic
dependencies and live receipts are retained in the
[live checkpoint](../../reports/2026_09_09_radio18_live_startup_checkpoint.md)
and [packaging checkpoint](../../reports/2026_09_09_scanner_bundle_release_checkpoint.md).
Third-party notices copied unchanged from the local build inputs accompany
the release under [scanner-glrt-licenses](scanner-glrt-licenses):
libiio LGPL-2.1, iiOD GPL-2, FFTW's COPYING, libxml2's Copyright, and zlib's
LICENSE. Keep exact source/build provenance and these notices with any promoted
artifact; this checkpoint is not a claim that external distribution is complete.
