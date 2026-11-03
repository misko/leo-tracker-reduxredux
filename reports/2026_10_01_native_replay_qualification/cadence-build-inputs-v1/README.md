# Preserved detector build inputs

These 29 source files were copied only after checking each byte digest against
`../ungated-glrt-pgo-v2/source-manifest.json`. `source-map.json` preserves the
original paths, snapshot-relative paths and digests. This adds durable source
provenance; it does not modify scientific fixtures or replace the qualified
archive. The source's README, license/provenance comments and kernel provenance
are retained without edits.

`detector/native_glrt.h` is the exact ABI header required by the archived GLRT
library. Its SHA256 is
`abbc657d54a37f4e7031200d4f91653d8d5a96ba1d2871e7d3924eb43f0c660f`.
Use this header directory when building the recorded replay wrapper against
`../ungated-glrt-pgo-v2/artifacts/libleo-native-glrt.a` (SHA256
`b2d26282e79664d278a0180a7c8421c75f6f719ae3b128563561ce4edd886971`).
The current maintained detector has additive interfaces and a different result
layout; do not mix that header with this frozen archive.

Use the repository's `native/adaptive/bench/build-recorded.sh`, passing the
output executable, this header directory, the archive, and the same ARM FFTW
float archive and double shared library used in the build receipts. The copy
of the script here records the qualified command; its relative source paths
are intended for the repository location, not execution in this snapshot.
The actual wrapper/runtime/projection sources and executable hashes remain
those recorded in each replay experiment. PGO training/build receipts and
profiles remain in `../ungated-glrt-pgo-v2/`; this snapshot is not a retraining
or a claim that arbitrary compiler/library versions reproduce identical code.

Device execution consumes the pinned binaries and local recording assets. It
does not import these source paths, the reference repositories, or host Python.
