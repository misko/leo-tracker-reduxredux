# Integrated direct-CI16 final scorer

This bounded experiment starts from the scientifically qualified
`limited-complex-v2` full search. It converts each CI16 window directly into
the workspace once and retains a narrow read-only CI16 view for integer-offset
final GLRT scoring. Candidate discovery, grids, fine FFT, boundary fallback,
and final score equations are unchanged. The explicit real/imaginary products
come from the qualified direct-CI16 scorer and prevent limited-complex lowering
from reintroducing generic complex division.

`python3 build.py` creates immutable host and ARM snapshots and executes only
host tests. `--arm-only` cross-builds without target execution. The CI16 API is
`leo_full_search_run_ci16(workspace, interleaved, scalar_stride, count, result)`;
the caller supplies the first I component and a stride in `int16_t` scalars.
This is the integration boundary available to a later frame-budget experiment.
