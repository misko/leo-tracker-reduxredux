# In-flight orbit support avoids the DS30-0022 restart

The repaired saved DS30-0022 worker finished in **34.634 s wall /
34.580 s CPU**, down from the authenticated **39.812 s / 39.781 s**
recovery. The single candidate saved **5.179 s wall (13.0%)**. It
reproduced the exact signed `orbit_support` terminal, both calibration
positions and RF results, all ordered owners, the 179-point grid,
recorded fit path and eight PNGs. No new baseline, waveform read, or
backing archive read occurred. [Original repaired control](solver-exception-0022.md)

| Measured boundary | Earlier restart | In-flight support |
| --- | ---: | ---: |
| Saved child through exit, wall / CPU, s | 39.812 / 39.781 | **34.634 / 34.580** |
| Numerical solve and evidence, wall / CPU, s | 36.624 / 36.594 | **31.393 / 31.354** |
| Preparation calls | 2 | **1** |
| Inference calls | 2 | **1** |
| Verified causal archive reads | 202 | **101** |
| Patched corner projections | 8 | 8 |
| Added orbit knot | −18 s | −18 s |

The previous child spent 1.862 CPU s preparing the abandoned attempt
and 3.266 CPU s entering and unwinding its failing inference. The
in-flight guard extended the already authenticated bank at the first
eligible out-of-domain lookup. Its scoped nominal projector and
causal extension are identical to the prior successful retry.
All eight projections used the same SGP4 propagation requests,
new states and original seam checks. The patch charged 27.0 ms
wall for the regional extension itself. Removing the repeated
preparation also removed 180,586,668 verified logical TLE bytes
from resident tmpfs. [Frozen method](live-orbit-support-protocol.md)

The same earlier-orbit census chose lean. The same later support cap
rejected the candidate after 131 of 2,159 curved rows, 13 of 258
predictive rows and five of 63 tracks would have been removed.
The existing named fallback then completed within the in-flight solve.
It returned the same 2,388 ordered observations per arm, exactly
matching the earlier v2 owner digests. Fixed-zero and fitted position
errors stayed **1.294 km and 1.311 km**, with conditional RF RMS
**161.796 Hz and 161.615 Hz**. The final owner list, path and grid
remain bound to the exact same published position image.

The adapter binds at the original installed solve entry. It applies no
recording or geographic policy. The original corner code consults its
extension only when the ordinary projector encounters the known
domain error in eligible receiver-smooth discovery. A successful
extension retains the visible `orbit_support` policy. Other solver
policies and the original retry factory remain available. The
component tests passed healthy queries through sparse and direct
native projections with identical numerical results and zero extra
propagation. Exact domain failure, supported edge expansion and
unrelated error propagation were also covered. **15 targeted tests
passed.**

Both processes ran with the same signed staged packet, archive,
earlier portable index, renderer and shared low-priority CPU 2
slot. Reusing the already admitted job required **0.340 s wall**
of launcher checking and font-cache preparation outside the candidate
clock. The historical preflight required 0.430 s to construct and
admit the saved scope. The child recorded 96 process input blocks
with zero major faults, compared with 408 inputs and seven faults
for its historical comparator. The input counters do not identify
which installed dependencies were read. This is one saved comparison
and gives no raw acquisition or healthy-recording throughput estimate.

Offline scoring initially compared decoded image dimension tuples with
serialized lists. Canonicalizing that metadata confirmed exact PNG
bytes and decoded pixels on all eight through the existing outputs.
No rerender or candidate rerun was needed.

Frozen execution `edd75eaef`. [Machine receipt](measurements/live-orbit-support-0022.json.gz),
SHA-256 `86ecd26746a59786fe4a92581b24edbf7c680af73309bdba6a8cb9f15b709770`
before compression.
