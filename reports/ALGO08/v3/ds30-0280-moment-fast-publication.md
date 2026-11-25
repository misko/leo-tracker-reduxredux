# Opt-in complete Graph port for moment-preserving CFO

The separate rank-68 entry uses the full released Graph port to form
the existing moment-preserving correction. It gives the held-odd
proposal Graph and the ordinary unedited Graph their own released
native path, vector-edge, and polynomial-cache scopes. The saved
worker records both sets of counters under
`moment_preserving.fast_graph_formation`. The edited Graph keeps its
original outer instrumentation and preparation boundary.
[Protocol](ds30-0280-moment-fast-publication-protocol.md) ·
[Measured Graph equivalence](moment-fast-graph.md)

Use the release interpreter and the new script with the normal capsule
arguments. Each future comparison starts from a fresh private `/tmp`
root and uses the existing verified rank-68 inputs. `prepare` emits the
readiness pin. The ordinary watch emits the gate pin consumed by the
corrected watch. The normal capsule launches the `child` subcommand.
The `score` subcommand takes the completed pre-survey closure pin.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
entry=/absolute/checkout/reports/ALGO08/v3/ds30_0280_moment_fast_publication.py
run=/tmp/new-rank68-fast-graph-run
launch=(sudo -n -u leo taskset -c 3 nice -n15 ionice -c3 env
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1
  "$release/venv/bin/python" -IB "$entry")

"${launch[@]}" prepare "$run"
"${launch[@]}" watch "$run" --cell ordinary --pin "$ready_pin" --driver-pid "$driver_pid"
"${launch[@]}" watch "$run" --cell corrected --pin "$ready_pin" --driver-pid "$driver_pid" --ordinary-gate-pin "$ordinary_pin"
"${launch[@]}" score "$run" --pin "$closure_pin"
```

The entry binds a new protocol and source list. The previous rank-68
extended script still supplies the independently launchable ordinary
and original moment-formation comparison. Timing and scientific
publication comparisons for the new entry require independently
matched saved runs.
[New entry](ds30_0280_moment_fast_publication.py) ·
[Established comparison entry](ds30_0280_moment_position_extended.py)

| Provenance input | SHA-256 |
|---|---|
| New protocol | `b066ca07e31d042bbbefdfe2ab5322595f76f3fec059d4223375a58bb44b0161` |
| New capsule source | `2e5ed6d16278b1d3abdda5870d63e528aa396d44a665a23ca999743082339962` |
| Generic Graph adapter | `74f0d1e865d92e95c4024d3d11b0502f9217e2e88abb83982d335f8cc5c9b28e` |
| Released Graph binary | `e623daaff9ac9fddc709d26af2a1fecd696aa133568c3d6c0a4d10e6b481d627` |
| Complete-port exact comparison | `b757315415ae137956362453b1329fde5047e5d1337861480e69dc433b662f84` |

The adapter takes an existing moment-formation module through
`moment_preserving_fast_graph.enabled(moment_module)`. A separately
registered DS30-0212 or held-case launcher can use that scope around
the current `attach_projected` or `child` interface and supply the
case's authenticated formation certificate. The adapter uses the
prepared stock boundary and has no case or location arguments.
[Reusable adapter](moment_preserving_fast_graph.py) ·
[DS30-0212 formation interface](ds30_0212_moment_preserving_publication.py)

The synthetic entry tests exercise both roles with the actual released
Graph, including compiled search in both corrected preparation
scopes, exact projection and a single independent edited Graph. They
also verify restoration when either preparation raises. This
integration used fixtures only.
[Fixture tests](../../../tests/pipeline_eval/test_moment_fast_publication.py)
