# Admission audit: iteration 150 and the clean 151 successor

This audit inspected source and persisted JSON field names, without model calls, reference-position queries, or disclosure of position-error values. It does **not** establish ground-truth leakage in iteration 150. An earlier review message described its inherited 107 baseline as reference-bearing before checking that artifact; that characterization was unsupported and is withdrawn.

## What iteration 150 actually gates

[150 run.py](../2026_10_10_position_error_iter150/run.py) invokes [148 preflight](../2026_10_10_position_error_iter148/run.py), which byte-hashes every `source_sha256` and `input_sha256` entry. The inherited 123 runner repeats that closure check. The frozen 150 protocol has 2,619 input entries and 1,567 source entries.

Relevant exact input-map keys include:

| Input key | Checked content and interpretation |
|---|---|
| `reports/2026_10_09_position_error_iter107/protocol.json` | Whole protocol bytes. The metadata scan found `reference_scope` explanatory text and historical path/hash maps, not direct receiver-reference or position-error fields. |
| `reports/2026_10_09_position_error_iter107/results/DS18-022/baseline.json` | Whole baseline receipt bytes. No direct reference/ground-truth/position-error field keys were found. Calling this receipt reference-bearing was incorrect. |
| `reports/2026_10_09_position_error_iter107/documents/DS18-022-baseline.json` | Sanitized public input document. No direct reference/error field keys were found. The runtime loader independently rejects such fields. |
| `reports/2026_10_09_position_error_iter123/results/native/result.json` | Historical native endpoint receipt, used as a post-terminal control comparator. No direct reference/error field keys were found. Its whole-byte hash remains a runtime dependency through the inherited closure. |
| Iteration 116 original point receipts, discovery traces, import/preflight receipts and search integrity | Historical inference provenance and native discovery state. These are pinned as whole artifacts, not selected by reference error in the successor. |

The field-name scan covered every JSON file directly listed in 150's input map. It found no direct keys naming receiver reference, ground truth, horizontal/position error, `error_km`, or `error_m`, apart from explanatory policy fields such as `reference_scope` and `no_reference_access`. Path strings containing `position_error_iter...` were explicitly excluded from field classification: the directory name does not make a document reference-bearing. This is a structural audit, not a universal proof about arbitrary free-text content.

A historical protocol can contain a digest of an older reference-bearing artifact. Hashing that protocol does **not** recursively open or hash every path named inside it. Changing an old artifact without changing this protocol therefore does not by itself alter this admission gate. Reissuing the protocol would alter its bytes, as would any other provenance edit. These distinctions matter when describing dependencies accurately.

## What enters the numerical decisions

[116 BoundCorpusLoader](../2026_10_09_position_error_iter116/corpus_port.py) checks the sanitized document, rejects reference/error field names, and invokes [105 load_case](../2026_10_09_position_error_iter105/run.py). That path prepares public observations, verifies recording/evidence identities, selects the causal TLE snapshot, constructs the regional bank from the supplied prior, and verifies bank ordering. Neither reference coordinates nor evaluation errors select the bank, discovery seed, retained region, calibration or fitted winner on this execution path.

[150 transition](../2026_10_10_position_error_iter150/transition.py) uses the original discovery state, arm-aware feasibility/stationarity and ordinary model objective. Its bounded promotion does not use geographical error. The reference-dependent reporting callback is behind the inherited both-branches-terminal reporting gate. The presence of historical loader files in a code-hash closure is not evidence that their load functions were invoked.

The motivating case and successive repairs are consumed, outcome-informed development. That is an experimental generalization limitation, distinct from injecting its reference position into numerical inference. The case must remain diagnostic rather than independent validation.

## Why 151 should still use clean projections

Fresh 151 search needs neither the motivating case's discovery cache nor its historical endpoint comparator. Rebuild its runtime input allowlist around the exact twelve membership identities, whitelisted inference documents, each member's model identity and five physical signatures. Keep broad historical preparation provenance and post-terminal evaluation authorities separate. This removes unnecessary dependencies without claiming that 150 used truth-guided numerical decisions.

Use [131 InferenceLoader](../2026_10_09_position_error_iter131/inference_loader.py) uniformly for all twelve. It checks observation content/order before bank construction, causal snapshot, compound evidence, prior/score and bank identities. It reconstructs with public ports and the same regional-bank policy; it does not call historical 51/85 admission loaders. The special need exposed by DS16-020 is missing direct-loader snapshot/bank metadata, not an excuse to drop that member or select replacement observations. Final 151 code and its explicit allowlist require independent review before freezing.
