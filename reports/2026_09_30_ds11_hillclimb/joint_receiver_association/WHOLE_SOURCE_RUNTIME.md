# Exact summation engineering continuation

The initial six-cell whole-source pilot finishes five cells; signed scan 0
times out at 90 seconds. Preserve its receipt and do not count it as a fit.
Accelerate only the exact DP: order sources by a deterministic track adjacency
elimination heuristic, enumerate only reachable partial states, and discard
states that cannot cover all tracks with the remaining sources. These are zero
support paths, not low-probability candidates. No objective, prior, calibration,
initial seed, bounds, stopping tolerances or fit cap changes.

Check the accelerated core with the same brute-force, normalization, sensitivity
and source-order tests. Before retry, replay both score and gradient at the
original scan-0 endpoint and the two completed signed endpoints (original 16,
additional 1): require score differences <1e-8 and derivative differences <1e-7.
Keep the original source file untouched and load an isolated adapter using the
equivalent partition function. Record timing. Only after parity passes, retry
the timed-out scan 0 from the same original seed with the same 90-second limit.
Keep the original timeout in the report and label the engineering continuation.
