# Deployment integration review while the prior sweep runs

This is an implementation review, not evidence of scientific qualification or
a deployment. The current candidate must first pass the frozen development
gates and a newly frozen validation protocol using the unopened iteration26
groups.

## Contract evidence

`src/leo/contracts/regional_position_v2.py` fixes schema version 2, analysis ID
`scanner-regional-position-v2`, protocol `sacramento-hard60-v1`, and
`refinement="off"`. Its public persisted semantics must remain immutable.
The proposed pipeline introduces joint clock/position refitting, candidate
pruning, RF-time correction and potentially satellite slope correction. A
versioned successor is needed; the old publication must not be relabeled as
the new model or overwritten.

The current presentation in `src/leo/presentation/regional_position.py` renders
coarse grid points and selected estimates from the public document. It does not
independently recompute Doppler predictions. A successor can retain the coarse
map while displaying the newly accepted final estimate, but must identify the
new pipeline and its actual selected/fallback stage truthfully.

## Concrete implementation scope after qualification

1. Move the qualified, tested numerical model and fitter into component-owned
   analysis modules. No runtime imports from report directories, reference
   repositories, storage, HTTP, CLI or PostgreSQL. Preserve the scientifically
   verified initialization and convergence behavior, including the initial
   joint-fit timing behavior and later-stage re-projection.
2. Add a versioned result contract and public reader/writer adapter. Persist
   physical nuisance corrections with their time/RF centers, priors, bound
   scope, satellite identities, stage provenance and explicit fallback status.
   Preserve the matched c-ablation scope and zero RF coefficient invariants.
3. Add application orchestration over the same observations and candidate bank:
   preserve ordinary finalists, add sep25 finalists, compare only the unchanged
   regional score, then run the qualified joint-clock sequence and final
   correction. Serialize reference errors only after inference. Reuse public
   checkpoint ports; do not construct another component's storage paths.
4. Give the new analysis its own source/configuration binding and publication
   namespace. The existing V2 CLI fingerprints broad `regional_position*.py`
   and `hard60*.py` numerical/application globs. Adding files under those names
   can unintentionally change V2's configuration digest and invalidate its
   completion check, so module naming/binding must be reviewed explicitly.
5. Add the new analysis to the standard worker with bounded, resumable execution.
   Readers/UI should prefer a completed new result and retain access to V2/V1
   historical results. Keep the existing longest-16 TLE review PNG behavior.
6. Test numerical equivalence against qualified report results, convergence
   fallbacks, strict zero-c locks, immutable publication/reader behavior,
   stage-resume behavior and rendering. Existing golden fixtures must not be
   updated merely to accommodate failures.
7. Perform a cold execution using the integrated code, compare the selected
   result and PNG to the qualified model, then stage/deploy. Verify actual
   worker source/configuration, new standard analysis publications, and PNG
   rendering through the live WebUI/API. A report PNG or offline cached replay
   alone is insufficient deployment evidence.

No production changes have been made by this review. No new RF collection is
needed or authorized by it; use existing recordings and independently occurring
published scans for verification.
