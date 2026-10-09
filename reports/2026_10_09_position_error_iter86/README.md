# Iteration86: pause-safe geometry-prior completion

The fixed geometry-overlap experiment is iteration84. It was explicitly paused
at129/148 completed members, with DS18-016 and DS18-017 in progress. Existing
workers resumed after all1375 frozen source/input hashes matched. The original
monotonic wall-time deadline can count suspended time. A separately frozen rule
therefore repeats both variants and both c arms for both pause-exposed members,
regardless of their original outcomes. That is eight new fits, four per member.
Original receipts are retained. The pause-exposed completed receipts later showed
ordinary0.7–1.6s elapsed and convergence; actual timing contamination is not proved.

The final148-member comparison always takes these two members from iteration86
and the other146 from iteration84. Missing retries stay pending; failed retries
stay explicit. Reference positions and errors never select the receipt or winner.
The original geometry prior and matched90s/600iteration budgets are unchanged.
Both arms share fitted-derived seed, bank and projector; c0 locks staticc and
RF-time terms. All members are consumed development, with no unseen validation
claim. Production B7 remains deployed and this experiment changes no defaults.

Run `freeze.py` once, then `evaluate.py`, then `report.py`. The wrapper calls the
unchanged hash-verified iteration84 evaluator with a separate output root. The
reporter reuses iteration84 metrics and rendering with an explicit source selector;
the in-memory protocol assertion view adapts to the composite report digest while
preserving `source_protocol_sha256` and `selected_source` in summary results.
`receipt-selection.json` records all148 source choices. No persisted original
receipt is rewritten or copied. [RESULTS.md](RESULTS.md) and
[comparison.png](comparison.png) are generated after completion.
