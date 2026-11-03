# Source-derived corrected detector geometry

`application/corrected_geometry` implements the geometry callback for the
additive scanner profile. It consumes composition-owned pilot IF/template
extents and validated visit authority, computes each receiver's baseband
center, and intersects both observable bandwidth limits with the configured
policy bound. It does not consume a candidate, score or reference answer.

The callback rejects invalid rates/layouts, unavailable template support,
nonfinite values, zero manifest digests, target/frequency mismatches, excessive
residual width, and inconsistent sample intervals. Failed calls leave the
output untouched. Successful calls bind the manifest, visit/counter/transition
authority, template extents and resulting geometry in a SHA-256 digest using
explicit little-endian integer and IEEE-754 encodings.

Host, ASAN/UBSAN, ARM cross-build and physical PLUTO+ tests pass. The host,
sanitizer and physical test outputs are byte-identical, including the geometry
authority digest. Tests cover the -312.5 kHz center calculation with ±800 kHz
policy bounds, asymmetric receiver clipping to ±100 kHz, repeated-call digest
stability, visit-dependent digest changes, and invalid-input rejection. These
are synthetic unit fixtures, not a fresh DS9 replay or RF measurement.

Build with `TMPDIR=/var/tmp bash
native/adaptive/application/build-corrected-geometry.sh MODE OUTPUT`, where
MODE is host, sanitize or arm. The physical test binary is installed only at
`/mnt/glrtbench/native-adaptive/tests/test-corrected-geometry`; the application
release is unchanged. Scanner/adapter integration remains separately tested.
