# Orbit-model endpoints do not improve original-IID optimization

Ten unique qualified endpoints from the preceding zero/orbit/linear fits were
used to initialize the original causal IID model on scans 0 and 16. All ten
processes completed; nine endpoints passed numerical qualification. None beat
the original qualified endpoint's training score by the frozen 1e-6-nat
replacement threshold. There were no retries or timeouts.

Both original positions therefore remain selected. Errors stay 765.072m and
2153.140m. The orbit model's alternative solutions provide no baseline
improvement through this recovery route. This closes this particular seed set,
not a proof of global optimality.

The original independent Student-t4/100Hz likelihood, causal candidate banks,
measurements, masks and bounds were unchanged. Every qualified prior endpoint
was considered, with only the frozen 1m/1ms deduplication rule. No reference
error selected an initializer or endpoint. Training selections were sealed
before geographic scoring.

Two tests pass for actual seed coverage, reference-independent deduplication
and failed-endpoint exclusion. Independent verification checks source hashes,
deduplication, all receipts, qualification, training-score replacement decisions
and unchanged error results. It does not independently rerun the optimizer.

See [protocol](PROTOCOL.md), [all attempts](selections.json),
[outcome](outcome.json) and [verification](verification.json).
