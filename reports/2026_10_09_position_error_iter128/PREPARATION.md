# Original-observation CFO re-extraction: adapter preparation only

Use exactly the already frozen110/117 random12 membership, without replacement,
quality filters or selecting where125 helped. Consume every originally selected
positioning observation for both receivers. Historical recordings and these
12 members are consumed development, not unseen validation. No IQ reads,
projection, native replay, position fits or source freeze have run here.

`adapter.py` is the component-owned pure boundary prototype. It requires a
complete expected window-ID list, immutable per-window original anchors and
acquired CFO, manifest-derived visit lengths, receiver ordering, a public
read-only visit callable and a baseline-parity/refinement callable. It checks
membership before reads, checks visit bytes before allocation, reads each
visit once, and retains explicit resource/unsupported/failed rows. It holds
only one raw visit and one converted20ms receiver probe at a time. Callback
workspace memory is additional and must be bounded separately.

Proposed raw-visit cap is32MiB, one process; source metadata can establish
whether this admits all visits **before** execution. Any larger visit remains
an explicit resource-cap row, not an excluded member. At10MS/s each converted
20ms complex128 probe occupies3.2MB, plus temporary conversion arrays and
kernel workspace. Native one-rate workspace is reused serially; no full-corpus
IQ array is retained. Total memory/time still require measured preflight.

The adapter permits2.5/10MS/s only as explicit candidate capabilities, **not**
proof of parity at10MS/s. Source shows integer symbol widths11/44 samples
respectively, so64-symbol spacing is uniform; fractional guards and exact
template values still need component/native synthetic validation at10MS/s.
Other rates produce explicit unsupported rows. No old2.5/5-only comparison
contract will be relabeled as covering10MS/s.

Outstanding before any freeze/execution:

1. Extract a sanitized exact12 membership authority from frozen110/117 metadata
   and original selected window IDs from their source-bound observations.
   Do not use reference errors or candidate improvements for selection.
2. Add a narrow public full-fractional-product projection retaining acquired
   CFO and original exact/control/fractional offset/rank. Reduced
   TrackingCandidate omits acquired CFO. Bind capture, analysis and projection
   digests; verify original selected rank/ID without new winner selection.
3. Connect public adaptive `read_visit_ci16` with exact valid-counter and probe
   start mapping. No private storage paths or ORM access; original support
   bounds and interpolation guards must fit the source window.
4. Implement the evaluate callback: reproduce original conditioned native
   scores/CFO, enforce matching native/Python spectrum winner, then apply
   unchanged125 variants. No reacquisition, changed epoch, gate or selected
   observation. Unsupported/historical-model/parity failures are retained.
5. Freeze membership, limits, exact sources and failure policy, then obtain
   parent review/publication before any IQ read. This preparation does not yet
   implement those production-source projections or numerical callbacks.

Four synthetic component tests currently cover unchanged anchors/sample count,
membership, explicit failure retention and resource/unsupported guards before
the read port. No real-IQ or native tests are included in that claim.
