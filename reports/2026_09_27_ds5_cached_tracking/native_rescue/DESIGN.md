# Bounded same-receiver rescue, development experiment

This candidate spends some measured native-detector headroom on a more thorough
search. It is not yet a qualified replacement or a measured speedup. Prior
development outcomes informed this design; reserved validation remains closed.

Run the unchanged causal NativeTradeoffDetector with the qualified numerical
boundary engine independently on both receivers. Preserve every native-positive
decision. If either receiver is inactive, select the first inactive receiver in
fixed order RX0, RX1. Permit exactly one additional 20 ms Python acquisition on
probe zero of that receiver, with the existing ten-candidate configuration and
conditioned GLRT scoring. No reference result, truth label, opposite-receiver
frequency, or future visit may select or seed this acquisition.

Consider retained candidates in their original deterministic order. A seed must
pass the existing Python conditioned margin gate. Measure the same candidate
through guarded native guided scoring on probe zero, then on fresh nonoverlapping
probe two of the same receiver. Preserve acquired/scoring frequency separately
from residual-corrected physical frequency. Transport frame timing in local
coordinates modulo the 750 Hz frame period, subtracting probe-start displacement
before normalization. Do not convert absolute source counters to floating point.

Both native observations must pass the existing status, bounds, fractional,
support-frame and margin gates. Require physical frequency agreement within
8 kHz and circular frame timing agreement within 2 microseconds. Stop at the
first passing pair; otherwise retain the original inactive decision. At most
ten seed and ten confirmation measurements are permitted. No extra acquisition,
later confirmation probe, threshold tuning or cross-receiver substitution is
allowed in this version. Rescue decisions do not train the native track cache;
the existing native cache continues to use its unchanged causal policy.

The Python function's word "conditioned" refers to the supplied epoch/frequency,
not nuisance-tone rejection. Native guided scoring also does not run blind
acquisition's nuisance conditioning. Consequently this rescue can reintroduce
false positives even when the primary detector rejects interference. Its timing
consistency gate compares transported point hypotheses, not independently fitted
epochs. These are explicit risks to test, not claimed protections; any constructed
false positive stops progression to the recorded-data stage.

Evaluate fixed existing development membership in sequence: 42 control/sequence
cases, 26 diagnostic cases, then 64 recorded visits. Compare the current
application, a separately stateful native tracked baseline, and the rescue
candidate. The control stage may omit the expensive application comparator,
using known constructed truth. Stop before later stages if constructed truth
checks fail. Freeze all implementation, runner, tests, input memberships and
dependencies before outcome inspection. One CPU core, one math-library thread,
one DSP campaign at a time; 120-second controls/diagnostic and 300-second real
limits. Save failures as immutable receipts rather than repairing frozen runs.

Include IQ conversion, proposal generation, confirmation and controller work in
complete-call timing. Exclude file reading, hashing and one-time initialization;
report that boundary. Measure aggregate CPU and wall latency distributions,
receiver and visit activity, reference identity retention, constructed truth,
extra detections, routes and fallback/rescue counts. Record raw immutability and
source hashes before and after. Do not multiply speedups from separate runs.

Before outcomes, add a separate mirrored-negative audit to the controls stage:
select every independent legacy control for which both receivers are constructed
negatives. Swap its two IQ receiver columns, use fresh detector instances and
require both outputs to remain inactive. This tests the second receiver's
interference under the fixed RX0-first rescue policy. Preserve the original 42
control occurrences; record audit results separately, with parent input hash,
derived input hash and explicit permutation. Do not label transformed arrays
with the original IQ hash. Both-receiver negative truth survives this permutation;
positive or causal sequence fixtures are not permuted in this audit.
Metadata inspection fixes this membership at 12 parents (six per sample rate):
six noise and six tone controls total. Select independent legacy cases with
`activity_policy == "required_inactive"`, `expected_active is False`, and both
receiver truths constructed-negative with no pilots. These are 12 paired
orientation checks, not 24 independent negative realizations. Mirror receiver
truth provenance as well as IQ and identify derived cases with `::rxswap-v1`.

The prior 18–22x planning estimate and 76/79 reference proposal ceiling are not
success criteria or measured results. Report what this actual algorithm does.
Receiver reference misses at 1%, 3% and 5% are comparison bands, not a license to
hide timing/frequency errors, constructed false positives or multisignal loss.
No holdout or reserved validation IQ, production changes, RF collection, or
QNAP writes are authorized by this experiment.
