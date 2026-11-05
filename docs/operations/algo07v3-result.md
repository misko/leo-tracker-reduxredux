# Standalone ALGO07v3 scientific result and publication

The owned application runs native GLRT preparation and all scientific policies
before producing a result. `build_evidence` projects that completed state into
portable values; `LocalizationV3Store.save` commits those values and all eight
PNG products before `publish_saved` exposes the existing WebUI manifest.
No earlier algorithm terminal, store or worker is required.

This implements the persistence/publication boundary. It does not yet provide
the production job scheduler or ordinary-clock admission qualification. The
[owned run/resume CLI](algo07v3-cli.md) now supplies tested process deadlines and
publication recovery under an explicit all-work validation policy.
Deployment remains disabled pending the plan's scientific and operational gates.

## Result contract

The version-one receipt is owned by `leo.contracts.localization_v3` and uses
model `algo07v3-exact-v1`. It binds the native run/session/input digest, policy
model, selected model, native point count, both arm summaries and the scientific
archive's digest and byte count. Its receipt digest becomes the public
`terminal_sha256`; this denotes the owned scientific terminal, not an invented
older algorithm terminal. Existing ALGO and WebUI contracts are unchanged.

The archive contains:

- Native preparation: observations, polynomial tracks, catalogue/orbit bank,
  noise, phase history and forecast.
- Recovery catalogue and scientific audit for each policy, including rejected
  trials and operational accounting. The qualification mapping excludes only
  previously declared timing fields; the archive retains those fields.
- Selected arms, exact native point owners, coefficients, phase/state values and
  calculated residual evidence.
- Plot inputs, grid/path evidence, all eight PNGs, rendering reference and
  configuration/implementation provenance.

Completed evidence must agree on native identities, ownership, owner digests,
point counts and endpoints before storage. Final recovery must be complete.
There is no pickle or persistence of live likelihood objects. This is a complete
result checkpoint, not mid-optimizer resumption.

## Lossless archive encoding

The archive is a ZIP with a versioned `values.json` tree and content-addressed
blobs. The tree distinguishes maps (ordered encoded key/value pairs), lists,
tuples, hexadecimal Python floats, numerical arrays and NumPy scalars. Dataclasses
become explicit field maps. Non-string mapping keys and NumPy dtype distinctions
are retained. NaN breaks in orbit curves remain representable.

Each distinct array is saved once as a non-pickle NPY blob and referred to by its
digest. Plain NumPy scalars use inline dtype and raw-byte hex, avoiding a ZIP
member and NPY header for every scalar. Structured scalars retain NPY metadata.
The decoder also accepts the initial qualification's scalar-blob form. Object
arrays/scalars are refused. Decoded arrays are shared read-only evidence.
PNG blobs are also content addressed. Duplicate, corrupt and unreferenced ZIP
members fail closed; archive members are read directly and never extracted.

The archive is written to a temporary local file, fsynced and linked to its
immutable content name. The scientific receipt is committed last using the
existing immutable JSON primitive. Incomplete saves have no completed receipt.
Repeated identical saves are idempotent; changed results under the same run are
rejected. Paths are confined, symlinked descendants are rejected, and QNAP output
roots are forbidden.

## Publication and restart boundary

`publish_saved(run_id, result_port, publication_port)` loads and verifies the
owned result and passes eight PNGs plus both sidecars to the existing public
standard-analysis publisher. It makes no numerical fit, TLE read or renderer
call. It never constructs another component's paths. The standard manifest is
the UI visibility boundary; incomplete publication can be retried from the
scientific result. Grid/path sidecars bind to the selected owners, terminal,
input and position PNG through the existing contract.

Evaluation coordinates enter only the already-completed rendering stage. The
saved reference is attached after standard publication, without changing the
scientific result. A conflicting saved publication reference is rejected before
publication. A crash between publication and reference attachment can repeat
the same operation safely.

Use public storage/application methods, not namespace paths, in other runtime
components. The private result namespace and ZIP layout are storage-owned.

## Qualification

`tools/check_algo07v3_publication.py` runs one native input through scientific
storage and standard publication in an explicitly supplied fresh output tree.
It validates the session and input digest, saves source bindings, reloads every
scientific field for exact comparison, checks all eight PNG bytes, checks both
sidecar bindings and repeats publication without fitting.

The [publication report](../../reports/2026_11_05_algo07v3_publication/README.md)
records the isolated native run, HTTP route verification, tests, timing scope and
subsequent exact scalar-encoding benchmark. The numerical scan and evaluation
reference never serve as alternate inference inputs. Publication qualification
on one retained-incumbent scan is not full population or production execution
qualification.
