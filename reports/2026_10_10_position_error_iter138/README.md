# Explicit successor to the iteration 136 import failure

All twelve iteration 136 members failed before model reconstruction. Its runner
imported the support adapter using the generic module name `adapter`. The reused
iteration 116 entrypoint imports its driver, which requests `PointEvaluator`
from its own adapter. Python reused the already-loaded iteration 136 adapter;
changing `sys.path` did not change that cached binding.

This successor loads the unchanged iteration 136 support, pairing and audit
modules under distinct names. Temporary aliases resolve their internal imports
and are restored before the corpus-loader import. The original functions retain
their module objects. No scientific function is copied or changed. The runner's
output directory changes to this explicit successor, so all original failures
and costs remain intact and are frozen as lineage.

The same twelve consumed members, original observations, support rules, saved
both-c endpoints, 125 Hz scale and objective parity checks apply. There are at
most two endpoint evaluations per member, no optimizer, IQ read, reference port,
correlation selection or position evaluation. All failures remain in coverage.
Exclusive claims and serial launch behavior are unchanged.

The subprocess regression imports the actual legacy entrypoint and verifies
its driver resolves the correct `PointEvaluator`, without constructing a corpus
loader or reading recordings. A separate regression reproduces the original
failure. Preparation alone does not authorize freezing or execution.
