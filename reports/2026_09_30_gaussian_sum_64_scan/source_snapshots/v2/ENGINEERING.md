# Numerical and artifact corrections before the final 64-scan replay

The first two batches exposed floating-point symmetry validation failures. A
mathematically symmetric projected covariance had mirrored entries differing by
about 1.05e-12 while its minimum eigenvalue was approximately 20,000. The strict
elementwise symmetry check rejected a few near-zero off-diagonal entries. The
same issue occurred in an innovation-covariance matrix product.

Revision 2 explicitly averages internally constructed covariances with their
transpose before validation. Caller-supplied covariances still undergo strict
validation. This restores the mathematical symmetry of the existing equations;
it changes no prior, likelihood, covariance parameter, approximation budget, or
scientific threshold. Component tests cover the roundoff case and retain rejection
of materially nonsymmetric input. Independent exact-Gaussian oracles remain gates.

The original state NPZ files also wrote hundreds of MB of mostly zero covariance
entries per arm. Processes were observed blocked in `balance_dirty_pages`; system
I/O pressure exceeded 70%, and several attempts timed out during artifact writing.
Revision 2 uses NumPy's lossless compressed NPZ format with identical float64
arrays and keys. Full states remain available and hash-bound. No resource limit
was raised, and no incomplete result is converted into a success.
A representative prior state compressed from 314,575,726 bytes to 393,995 bytes
with bitwise-identical arrays after reloading; see compression-check.json.
Remaining orbit exports may use the owned SSD cache rather than a stalled bulk
volume. Their catalogue, time grid, precision, source bindings and numerical values
are unchanged; export failures and exact-source engineering retries are retained.

Original attempts remain under `runs/`, with their source snapshots under
`source_snapshots/v1/` and their state files in the original bulk subdirectory.
The complete final panel is independently rerun under `runs-v2/`; its state files
live under `/srv/bulk/leo/research/gaussian_sum_64_scan/states/v2/`. The evaluator
uses only that revision for the 64-scan / 192-arm primary denominator. Earlier
attempts are superseded engineering trials, never additional independent scans.

The Sacramento prior, scan selection, all numerical/scientific budgets, and the
failure/abstention rules are unchanged across these engineering revisions.
