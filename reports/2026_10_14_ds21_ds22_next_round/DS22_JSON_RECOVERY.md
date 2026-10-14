# DS22 first-discovery preparation compatibility recovery

The first DS22-001 discovery attempt stopped after 31.967 seconds during
training reconstruction, before any bank, point or optimizer call. Its failed
slice remains in `local/ds22-discovery-v1/DS22-001`; it is not continued.
The immutable provider and discovery v1 sources remain unchanged.

The training-only diagnostic `local/ds22-roundtrip-audit-v1` completed in
32.760 seconds with zero optimizer/orbit calls and no held or reference use.
It reconstructed the original training data and verified the provider authority
before and after. The entire census and all three prepared-evidence digests
match. Exactly six raw comparison differences occur at
`training_frames/{all,low,high}/{receivers,high_fractions}`: dataclass tuples
are persisted by JSON as lists. JSON-canonical reconstructed fields match the
persisted fields exactly. There is no numeric tolerance or changed evidence.
The audit tool's bytes match the source digest recorded at execution:
`20db1c55ccd388c15ff40164b1ef0cc311f1f2eb19dff48d897eab9b8c4ebb31`.

`ds22_json_training_provider.py` is an explicit consumer compatibility adapter
over the genuine frozen DS22 provider. It retains the original authority and
numerical preparation ports, performs exact comparison in the persisted JSON
representation, and rechecks parent authority after reconstruction. It neither
repairs existing files nor impersonates DS21 membership.

`ds22_json_fitted_discovery.py` retains the original discovery math, training
selector, fit limits and 480/495/500-second slice budget. Its separate schema
and source closure bind the compatibility adapter. The small original facade
is preserved as a separate file because its functions use module globals;
changing those globals would invalidate the frozen predecessor. Only its
provider import, schema and documentation differ from the original facade.

The explicitly authorized recovery uses a new namespace,
`local/ds22-json-discovery-v1/DS22-001`, with the original completed provider
as parent. The failed pre-bank attempt and diagnostic remain separate evidence.
No failed fit is rerun, and no checkpoint continuation is automatic.

Tests exercise public synthetic partitioning, candidate projection, trajectory
reconstruction, prepared observations, calibration frames, receipt writing and
reading, and real reconstruction. They reproduce exactly the six tuple/list
differences, demonstrate the old loader's rejection and the adapter's success,
and reject 1e-9 changes to numeric frame values. Twelve discovery lifecycle and
real saved-bank/point/terminal validation tests also qualify the new facade.

This establishes preparation compatibility, not DS22 position accuracy.
The run remains the shared-discovery baseline; independent half-only discovery
and initialization controls are still outstanding.
