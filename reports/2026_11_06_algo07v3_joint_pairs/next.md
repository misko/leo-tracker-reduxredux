# Next measured target: phase-integral CPU work

The observer described below is now complete: six exact captured calls, all
original direct-mode results preserved, and unchanged inputs. See
[the measured table](kernel-profile/timings.md). On the largest grid, direct
cross-family contractions and right-hand-side construction account for 63.82%
of whole-call CPU, while optimized solve/determinant uses 49.94%. The next
implementation experiment is a bounded contraction-layout prototype, not
another whole-worker scheduling trial. Reject any changed output at the cheap
capture gate; preserve the actual summation order and both contraction modes.

The preceding native profile attributes 70.3% of DS26-0102 numerical recovery
to joint fits and their audits. The retained LU reuse removes a duplicate
factorization and saves about 5–7% on actual captured kernels. Audit and paired
fit concurrency trade CPU for latency; complete scan timing varies considerably
on this shared host. Neither mechanism establishes an improvement in queue
throughput. Scalar-only scoring and endpoint-result reuse are already rejected
after mixed or flat exact measurements and should not be repeated unchanged.

To reproduce the attribution before choosing another arithmetic optimization, run the external
`tools/profile_algo07v3_joint_statements.py` observer on the three native phase
grids used by the preceding direct-chunk qualification. The observer instruments
assignments in a private copy of the owned function. It does not patch the
runtime, alter contractions, omit diagnostics or change chunk sizes. Eight
tests cover full output/input equality, both contraction modes, three chunk
sizes, validation and the expected factorization call counts. Its initial test
failure was an assertion expecting tuple labels without the parentheses emitted
by `ast.unparse`; the labels are now checked correctly. All numerical equality
assertions passed in that initial run too.

Run this only after the predeclared native pair sequence completes, with one
CPU and one BLAS thread. Bind original native inputs and result signatures,
the current owned kernel and LU extension, and both actual BLAS libraries.
Each grid has one ordinary and one observed call in each contraction mode.
Require complete direct-mode results to equal the original native captures,
and all observed outputs to equal their uninstrumented counterparts. Preserve
invalid or failing captures rather than replacing them with synthetic inputs.

The result is attribution, not a speed benchmark. Assignment clocks exclude
unobserved guards, return-expression work and observation overhead; report the
whole call and unassigned remainder separately. Do not sum a containing fit
or stage with the nested kernel. Choose a subsequent candidate only after
identifying a material cost. In particular, changed memory layout may alter
NumPy contraction arithmetic even if the mathematical expression is the same;
it must pass exact captured-call comparisons before complete fits or native
qualification. Keep numerical budgets, observations, all audits and both
calibration arms unchanged.

Reproduce in the qualification checkout, selecting a fresh local output:

```sh
PYTHONPATH=src:tools:. OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 taskset -c 0 \
  timeout 120 /home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python -B \
  tools/profile_algo07v3_joint_statements.py \
  --native /srv/bulk/leo-dev/algo07v3-direct-chunks-native-0102-20261106 \
  --output /absolute/fresh-local-profile
```

Render a completed profile using this report's `render_statements.py --root
PROFILE --output FRESH_SUMMARY`. The renderer validates source bindings and all
six complete equality results before producing its table and figure.
