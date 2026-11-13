# DS29 metadata mint review

Status: source review, census accounting, final sealed membership coverage and
full source-metadata verification passed. No numerical inference or additional broad census was
run, and no mint, input or previous dataset authority was edited.

The reviewed freeze selects whole acquisitions whose earliest actual sample
time is in `[1793543987024292987, 1794545700000000000)`. It retains incomplete
recordings and absent tracking contracts, passes `required_channels=None`,
and has no rate, readiness, signal-quality or localization-quality gate.
Nonempty acquisitions use the pinned chunk-content identity; acquisitions with
no chunks use sorted segment-manifest hashes so unrelated empty failures are
not all assigned the same empty-content identity. Parent identity overlap is
rejected. The output is separate from existing dataset authorities.

Independent accounting of the saved discovery receipt gives 24 existing roots,
25,443 checked manifests, 615 eligible fast roots, 612 adaptive-format manifest
exclusions and zero errors. These are acquisition-root counts before final
content deduplication. Final DS29 has 615 unique acquisitions, exactly covering
all 615 discovered fast roots with no missing or unexpected roots: 612 complete
and 3 incomplete, with 612 available tracking contracts. All 615 happen to be
10 MHz; the collector does not impose that rate. Recorded integrity-error count
is zero. All three owned
mint tests passed when independently rerun with bytecode and pytest cache
disabled. Tests cover lower/upper boundaries, whole-acquisition grouping,
deduplication, parent overlap, empty failures, multiple sample rates, retained
incompleteness and adaptive-format exclusion.

The copied `freeze_ds28.py`, `freeze_ds23_dataset.py`, `mint.py` and
`raw_inventory.py` hashes exactly match the source bindings already recorded in
the DS28 revision 2 parent manifest. The DS29 adapter's deviations are explicit
and are exercised by its owned tests.

Reviewed SHA256 bindings:

| Artifact | SHA256 |
|---|---|
| freeze_ds29.py | 36eecfa28473e1eb88c292be21975b2436c1e38ffb95488b90739628e8417bb0 |
| verify_ds29.py | 204c3fa4e8d4925cada394022091b9884ed208e897f294c256537b2a48293733 |
| test_freeze_ds29.py | a4c41c2820a62025f3633c93b7881a703efa811f9ab3abf779320d07145f3f0b |
| discovery.json | 069b41d12f8d8a74006d8c3f8c6d46dc06abe3e36c7ed8f1b418bae1008bf944 |
| DS28 revision 2 parent manifest | 6bf59b01b5fbf72b42fafee2445cafde3c3660a10b0cb048a98a8340a2329e71 |
| Final DS29 manifest | b9b7dfc497f1df45e913e175be9b9471b1e0b49eab601f0aeff640c5c05c61a8 |

No demonstrated membership defect was found in the reviewed source. Every
source-code binding matches, and the preserved parent bytes exactly match the
existing DS28 revision 2 authority. The separate discovered-root coverage check
passed. The standalone metadata verifier passed: 10,424 metadata sources checked,
all final content identities and acquisition times recomputed, zero parent
content overlap, and source receipts, seal and evaluation units verified.
Acquisition starts range from 1793546660225325720 to 1794544542381528643 UTC ns,
within the declared interval. The generated receipt is
`ds29-independent-verification.json` alongside this review. The
standalone verifier checks final-member integrity but does not itself reconcile
discovered-root coverage; the independent coverage reconciliation above closes
that gap. IQ payload contents
are not rehashed by this metadata mint, and the metadata snapshot is explicitly
non-atomic.
