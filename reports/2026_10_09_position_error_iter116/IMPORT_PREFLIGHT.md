# Receipt-only import preflight: queue scores versus later presentation scores

The explicitly authorized pilot remains consumed DS18-022; no other recording
was selected. Public receipt inspection found a whole-prior bank of **877**
satellites, not the earlier 145-satellite regional union. Actual propagation and
rescoring costs for that bank remain unmeasured.

The original ordinary coarse receipts are accessible through the public
`RegionalCheckpointStore` port. The frozen sanitized iteration107 document
retains the 400 point coordinates/spacings but omits score values. Supplying the
sealed iteration107 baseline's displayed score trace caused the strict importer
to stop: five displayed objectives differ from original public objectives,
by about 14–872 NLL units. No import bundle or protocol was published, no hashes
were invented, and no mismatch was ignored.

Source inspection explains why:

- [hard60_runner.py](../../src/leo/application/hard60_runner.py) completes
  `hierarchical_search` before calling `recover_failed_coarse`.
- [hard60_recovery.py](../../src/leo/application/hard60_recovery.py) retries
  failed 40 km coarse fits with the bounded fitter, reranks existing regions,
  and replaces **presentation copies** of fits and search scores after the
  original queue is finished. It retains immutable original point checkpoints
  and also records `recovery.coarse[].original`.

Therefore the displayed final score attached to a coarse point is not always
the score that originally drove refinement. Replaying recovered endpoints in
the queue would create a different algorithm. A valid pre-recovery queue gate
must restore the original scores through independently bound original receipts,
verify that the ordered coordinates still reproduce exactly, and preserve the
separate recovered presentation trace for provenance. It must not silently use
post-search recovery for some old points while giving new candidate points only
ordinary fits.

The smallest scientifically clean scope is the **pre-recovery queue-allocation
comparison** from the draft. It does not claim that its raw retained regions
are the deployed post-recovery winners. Any operational retention/final-position
comparison needs the same subsequent recovery policy on both search inventories.
This scope was subsequently approved. The completed receipt-only restoration,
exact 400-point scalar replay and immutable bundle are documented in
[PROVENANCE.md](PROVENANCE.md). The experiment itself remains unfrozen.

[freeze.py](freeze.py) is a minimal explicit preparation API, not an executed
freeze. It requires full reconstructed observation/bank/prior hashes from an
authorized preflight. Those cannot be inferred from the saved metadata alone;
reconstruction remains deferred while numerical slots are occupied. It also
requires exact ordinary inventory coverage, numerical source compatibility,
sanitized document hashes and the previously named pilot. The sole tolerated
historical source mismatch is the already-approved non-numerical report renderer;
its mismatch remains disclosed. No arbitrary source mismatch is accepted.

All work here was source/receipt inspection and synthetic testing. No recording
orbit propagation, objective evaluation, fitter, new RF collection, freeze,
commit or push occurred.
