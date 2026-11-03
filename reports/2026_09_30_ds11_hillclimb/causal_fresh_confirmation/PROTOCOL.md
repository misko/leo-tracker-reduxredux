# Prospective causal-fresh confirmation export protocol

Freeze all five full-manifest DS11 recordings selected by the completed
metadata-only remaining-43 census: indices **10, 18, 35, 60 and 75**. Selection
uses only capture time, the 505-second guard, archived element metadata and
pre-capture local publication evidence. It does not use a position fit,
reference coordinate, residual, candidate bank or held score. Export all five,
including any row whose eventual frozen shortlist has no updated candidate.

Use the unchanged `tools/ds7_export_baseline.py` twice per row: first export the
original observation document, then its candidate bank. Preserve the DS11
minted manifest row, original track membership, train/held mask, candidate
policy, t4/100 configuration, catalogue divisor and strict causal 505-second
guard. Verify the observation's analysis-manifest digest against the minted
local analysis evidence and replay the exported document through the unchanged
fast baseline loader.

Run one export worker at a time with BLAS/OMP limited to one thread, `nice 19`,
and a 180-second process cap. Create one terminal receipt and combined log for
every attempt. Preserve timeout, failure and partial output; do not retry,
replace a row or expand the budget without a new recorded decision.

After all five attempts are terminal, assemble `plan.json` only from successful
validated exports. A complete confirmation input requires 5/5 successes.
Create a digest-bound physical-identity sidecar by mapping every bank catalogue
row to its archived NORAD, preserving exact track and candidate order. Intersect
those identities with the census comparison
`three_day_best_capture_vs_latest_provider_guard`, restricted to records with a
newer epoch and changed SGP4 inputs. Report every row, including zero affected
tracks/slots, and bind the census, original bank artifacts, archive sources and
pre-capture completion evidence.

This preparation authorizes no position fit. A later model may replace state
arrays only at the identified original candidate slots after exact old-element
replay. The five rows are an exposed, metadata-selected confirmation panel; the
reference coordinate may enter only after a separately frozen fit protocol and
all endpoint selections are complete. No RF is collected or changed.
