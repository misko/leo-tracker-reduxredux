# DS9-F001 proposal v2 source snapshot

The v2 receipt directly binds `0-acquire.py` and `1-geoid.py`; their hashes match
the receipt. `2-rf.py` is the imported vectorized likelihood implementation used
by acquisition. The receipt did not bind that transitive source directly, so it
is preserved here with its SHA-256 recorded in `bindings.json` rather than
represented as receipt-bound.

The working `acquire.py` subsequently changed only its `sys.path` setup from
front insertion to append, preventing report modules from shadowing application
modules. This snapshot preserves the exact receipt-bound proposal source.
