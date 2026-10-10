# Shard 0 launch deviation

Shard 0 was launched through `/opt/leo-tracker/current-api/.venv/bin/python`,
not the requested immutable 47e release path. The alias resolves to release
17484895464c225ebba977487aa36d3d81658bd8. The running process was preserved;
there was no restart or additional fit.

ENVIRONMENT_AUDIT.json records the exact command, both installation manifests,
all nine differing paths and their hashes, interpreter and pyvenv identities,
and 92 distinct shared libraries loaded by the first DS16-020 child. Every
observed loaded package library matches the requested release byte for byte,
including NumPy and SciPy BLAS libraries. The differing installed Leo native
acquisition library was not loaded. Repository Leo and hard60_runner import
origins were confirmed using PYTHONPATH=src:. without recording model calls.

This supports equivalence of the observed numerical dependencies, not identical
whole installations or an immutable-path launch. The alias must be monitored at
child transitions. Only PYTHONPATH and thread settings were read from the child
environment; no other environment values were persisted. Audit files are
postlaunch provenance outside the frozen scientific closure.
