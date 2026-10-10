# Independent preparation review

Root and the independent numerical reviewer found no blocking issue in this
successor. This review uses source inspection and synthetic tests, not recording
fits or reference-position evaluation.

The new port invokes the existing bounded fitter at the original discovery
position, with c free, unchanged physical constraints, and a five-second,
200-iteration optimizer budget. It independently audits the returned state even
when the saved convergence flag is true. Only an unqualified returned state is
eligible for the existing two-round, 100-evaluation Newton polish. The final
0.001 stationarity threshold remains unchanged.

The bounded fitter selects the lowest-objective independently qualified candidate
when one is available, otherwise its best feasible state. Its full diagnostics,
including terminal and best-feasible states, survive serialization through the
production `json_value` helper. The added integration test exercises real
`PositionFit` objects and the actual `_Problem` constraints with synthetic data.

The original discovery payload and identity remain unchanged. A copied seed
prevents accidental mutation. Returned fits and solver diagnostics remain in
failure receipts if a subsequent audit fails. Initial diagnostic errors remain
explicit inherited stage failures; they cannot admit a position. No previous
iteration's promoted numerical state is reused.

Tests cover original-state rejection, copied seeds, timeout and missing-fit
failures, infeasible or worsening fits, moved positions, unnecessary-polish
avoidance, independent qualification, recovery-port isolation, fresh output
paths, and the both-terminal reporting gate. The review reported 14 passing
tests under the pinned production interpreter. Root repeats this check before
freezing the protocol.

The optimizer deadline does not include all postfit summaries and audits;
recorded stage wall time is the cost measure. This is a single consumed-case
mechanism test, not independent validation or deployment evidence.
