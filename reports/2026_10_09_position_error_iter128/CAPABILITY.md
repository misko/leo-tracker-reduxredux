# Original analysis path versus research native capability

No recording IQ was read. Eight component/synthetic tests passed under the
production interpreter in1.01s. The tests cover2.5/10MS/s, lower/integer and
upper/fractional .27sample configurations, plus adapter membership/resource
guards. The synthetic tests are not operational-recording parity evidence.

The initial test correctly exposed a capability mismatch: the unchanged
[research native presence constructor](../../src/leo/analysis/native_presence/presence.c#L306)
accepts only2.5/5MS/s, so its10MS/s workspace creation fails. No macro or native
source was altered to bypass that guard. It is **not** evidence that original
10MS/s positioning measurements are unsupported.

The [host10MS/s analyzer](../../src/leo/scanner/host_adaptive_analysis.py#L136)
delegates to [adaptive `_analyze_loaded_visit`](../../src/leo/scanner/adaptive_hop_analysis.py#L611),
which calls `analyze_glrt64_dwell`. Its [detector](../../src/leo/scanner/detector.py#L133)
uses the Python conditioned/fractional score implementation. That
[public conditioned scorer](../../src/leo/analysis/starlink/pilot_methods.py#L726)
supports the integer11/44sample symbol geometry at2.5/10MS/s, respectively.
The numerical callback now exposes two explicitly named paths: original
Python conditioned scorer, or the research native presence differential oracle.
No automatic catch-and-fallback from native failure exists.

At10MS/s the synthetic test first asserts the native constructor rejection,
then tests original-Python baseline versus independent autocorrelation/refinement
reconstruction. At2.5MS/s it checks native versus original-Python baseline and
the independent reconstruction. The baseline CFO and both exact/control scores
must agree before either refinement is admitted. Stored original pass/fail is
preserved; callback output labels the scorer used. No new detection threshold
is inferred from these tests.

For actual recorded products, source-bound analyzer configuration and historical
provenance must authorize the Python path explicitly. A named analyzer version
does not uniquely prove historical compiler/runtime identity. Current templates
and numerical sources will be hashed at freeze; actual original score/CFO parity
is mandatory and cannot be waived when historical build identity is unavailable.
Missing or mismatched cases remain failures, not re-acquired replacements.

Initial metadata preparation receipts are preserved under `metadata/`: all12
failed an incorrectly formulated assertion comparing the prepared-window digest
to the document's compound digest. This was an adapter error, not a changed
recording. `metadata-v2/` reconstructs exactly the CLI compound hash from the
prepared-window digest, causal TLE snapshot digest and ordered eligible catalogue
IDs, using public metadata readers only. No orbit propagation or objective
evaluation is required. The old S14 report additionally omits the standalone
snapshot field; the compound digest still cryptographically binds that value,
so a separately recorded follow-up checks the compound without requiring a
redundant field absent from that historical report. Original failed receipts
are retained rather than overwritten.
