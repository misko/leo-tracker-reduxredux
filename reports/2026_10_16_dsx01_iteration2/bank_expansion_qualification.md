# Original causal-bank expansion: adapter and eligibility qualification

The omission is real within the original candidate-generation authority. S01's selected 46-candidate bank excludes 69433, but its original 987-candidate regional bank includes it. S05's selected 32-candidate bank excludes 57864, but its original 821-candidate regional bank includes it. These IDs are retrospective diagnostic examples here; neither appears in the expansion algorithm or its generic candidate-selection rules. Eligibility alone does not establish satellite identity or a recoverable association.

Both original regional banks use Hugging Face snapshot digest `sha256:2439873f2415acb0df93d408560a30cff267a666be312cfaa6a2734bbd8db197`, with their distinct original collection times: S01 `1792166536105889082`, S05 `1792188188945437726`. Both precede the corresponding recording origins. The adapter resolves the exact digest AND collection through the local read-only archive; it never chooses a newer snapshot or a different provider. It rebuilds only the terminal's original regional candidate inventory and requires the same eligibility afterward. All selected original orbit arrays and interpolation nodes must be byte-identical.

The canonical S01 report directory has no cached `orbit-bank.npz`; its full regional bank is rebuilt from that exact original authority. S05's `reports/new-three-segments-20261016/orbit-bank.npz` contains all 821 candidates, including 57864, with nodes from -21 to 321 seconds. The full cache was verified byte-identical against the causal reconstruction, not merely trusted from its filename. The qualification JSON records its digest and exact original selected/full number inventories.

## Narrow ports

`regional_bank(context)` returns the original full regional `PositionOrbitBank`. Optional `return_receipt=True` returns `(bank, authority_receipt)`. It does not inspect measured CFOs or rank candidates. `expandable_context(context, numbers, regional=bank)` returns `(expanded_context, transport_receipt)` and admits at most eight unique new eligible integer catalogue IDs. It retains every original candidate in its original order and appends additions in numeric order. Duplicate, already-selected, ineligible and malformed additions fail explicitly. With no additions it returns the identical context with zero work.

The parent owns generic full-training regional profiles and their evidence-based ranking; this adapter does not read DSX window membership, challenge hypotheses, station coordinates or held measurement values. The same selected expanded bank must be used for the expanded baseline continuation and the proposed training algorithm. Cross-bank objective comparisons are not used to select an expansion.

The rebuilt objective is the genuine existing `SharedScanObjective`, with the same observations, training mask, common-clock nodes/design/prior, original affine/RF correction coefficients, fixed high-minus-low contrast function and constant contrast prior, original score/visibility policy and existing q budget1.6. The fixed contrast is recovered from the old baseline function and validated at every original row; a nonstandard baseline fails instead of being silently approximated. Both training and full evaluation model objects are rebuilt in the same frame. No free group or per-track frequency term is introduced; c=0 context state is preserved.

Existing satellite total timing shifts are copied by unchanged candidate order, and added shifts start at zero. They are then represented in the new common/zero-sum timing coordinates. Consequently the common and relative coordinates and their implied prior penalties can change under a larger bank even while every old physical total timing remains unchanged. This is a declared bank-expansion effect under the unchanged prior equations, not a claim of exact cross-bank objective nesting.

Likewise, exact preservation of every old positive q and addition of positive new q is impossible at a fixed total budget. The declared target is old probabilities times `K/(K+m)`, with each addition assigned `budget/(K+m)`. The centered target logits are projected into the expanded objective's existing bounded ±2 zero-sum coordinates. If needed, one bounded linear least-squares projection is counted and its active bounds, logit error and actual probability errors reported. No clipping, extra detection budget, new q prior or fitted expansion-specific likelihood is used. Other nuisance coordinates are carried unchanged.

## Actual-data transport checks, no localization fits

The finite external qualification process used TERM135/KILL140 and completed successfully. Each case tested deterministic first-one and first-eight omitted regional catalogue numbers, unrelated to the retrospective example identities. These are adapter probes, not an approved expansion selection. The raw full regional causal reconstruction and cache checks are included in the elapsed time.

| Case | Original / regional | Qualification seconds | Maximum calibration error Hz | Maximum old timing error s | Maximum q probability target error |
|---|---|---:|---:|---:|---:|
| S01 | 46 / 987 | 22.492427 | 0 | 5.329071e-15 | 5.551115e-17 |
| S05 | 32 / 821 | 20.027269 | 0 | 3.552714e-15 | 1.249001e-16 |

All four expanded vector/nuisance states are finite. The q target was feasible without bounded-LS adjustment in these four actual probes, with no active q bounds and the original budget1.6 retained. This does not claim exact old-q preservation: the intentional proportional mass redistribution is described above. New timing seeds are zero to numerical precision.

The adapter performs **zero objective evaluations and zero localization fits**. Loading the two original contexts uses the existing common loader's strict source audit and baseline measurement, two source replay objective calls per case; preparation/reconstruction is not claimed to be free. Existing source bindings and public output receipts are read-only. No production writes, new RF or golden-fixture changes occurred.

Owned tests cover genuine original model execution after expansion, exact correction/clock/timing/state transport, masked held-CFO perturbation invariance, fixed-c preservation, eligibility/shape failures and changed common orbit rejection. A separate narrow synthetic-bound test exercises bounded-LS error reporting rather than clipping. The actual probability/transport details and authority receipts are saved in `bank_expansion_qualification.json`. No claim of improved association, excluded prediction or position follows from this adapter qualification; candidate profiling and matched optimization remain separate work.
