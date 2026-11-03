# Corrected detector profile adapter v1

This is the first narrow adapter from the additive scanner profile port to the
frozen corrected wideband detector.  It is an explicit, separate composition:
the adapter executable links only the corrected detector archive, and the
ordinary detector archive is not linked into the same process.

The adapter accepts only the qualified corrected profile: 7.5 MS/s, two
receivers, 20 ms probes spaced by 120 ms, serialized analysis, 22 coarse-CFO
storage slots, 22 peer-fallback symbols, and residual spans no wider than
1.6 MHz.  It rejects missing authority digests, malformed layouts, unsupported
dwell lengths, and concurrent use of one detector context.  The scanner owns
the byte-for-byte check between the geometry port's profile manifest digest and
the copied visit geometry; the adapter requires both geometry digests to be
nonzero and otherwise treats them as opaque authority.

Private corrected detector results cross a neutral value bridge and are then
copied field by field into the public result.  Neither boundary casts nor
copies whole private/public structures.  Independent review accounted for all
31 public candidate fields and all 37 public row fields.  The four additional
private interval diagnostic fields and three additional private capability
words do not cross the public boundary.

The adapter advertises `fractional_epoch_server_parity_qualified = 0`.
Corrected candidate recovery is qualified by the saved-data reports, but this
adapter does not claim full server detector parity, real-time operation, live
RF qualification, or deployment.

## Frozen-source binding

The bridge backend is the only translation unit that includes the private
corrected header.  It uses an angle include, and the build places the frozen
source directory before every worktree include directory.  Each build emits a
dependency file and rejects the build unless that file names the frozen header
and omits the mutable worktree header.  The retained ARM dependency file is
`artifacts/arm/corrected_profile_backend.d`; the host and sanitizer dependency
files are under `provenance/`.

The corrected implementation is the qualified source at
`ds9/receiver-authority-ablation-v1/wideband-research/source/native/adaptive/detector`.
The build script pins the four source files that establish the private ABI,
22-slot storage, peer recovery, and 1.6 MHz geometry.  The source snapshot in
`source/` contains the new neutral bridge, adapter, scanner profile contract,
test, and build script.

## Qualification

Host, ASAN/UBSAN, and TSAN runs execute the real corrected detector on saved
visit 276, in addition to focused conversion and failure-path tests.  They
verify:

- every common candidate and row field through synthetic and real conversion;
- fail-closed malformed row count, receiver, probe start, and candidate count;
- exact template length preflight, including zero and `SIZE_MAX`;
- capability and geometry restrictions, nonzero authority digests, and zeroed
  output on analysis rejection;
- exact public-adapter versus direct-neutral-backend candidates; and
- same-context serialization, with one concurrent call succeeding and the
  other returning `-EBUSY`.

The ARM binary passed the focused conversion suite under QEMU and the full
saved-dwell test on the physical ARM target.  The physical run used retained
visit 301 and completed all three corrected analyses in 166.911554828 seconds
wall / 166.888036 seconds CPU with 70,368 KiB maximum RSS and exit zero.  The
test does not bind a visit identifier or expected candidate values: any
7,200,000-byte, 120 ms, dual-receiver saved dwell is valid when the corrected
closure returns eight candidates for both rows.  Host qualification used visit
276; the physical qualification used visit 301 with the same authority
geometry.

Reproduction commands and all hashes are in `qualification.json`.  This is a
CPU-only, saved-data adapter qualification.  It did not capture RF or start a
service.
