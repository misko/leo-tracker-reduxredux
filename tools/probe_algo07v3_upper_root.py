"""External follow-up: reuse lower LU and solve the upper root without factoring it.

The transpose of the Cholesky root is already upper triangular. This experiment
supplies it to GETRS with identity pivots, preserving separate right-hand sides.
The original kernel still executes and every returned byte must agree.
"""

import hashlib
import json
import sys
from pathlib import Path

import probe_algo07v3_factor_reuse as probe

base_factory = probe.candidate_function


def candidate_function():
    function, original, source = base_factory()
    needle = "np.linalg.solve(root.T, solve_factor(lu, pivots, rhs))"
    if source.count(needle) != 1:
        raise ValueError("Unexpected separate-RHS prototype")
    code = source.replace(
        needle,
        "solve_factor(root.T, np.arange(width, dtype=np.int32), solve_factor(lu, pivots, rhs))",
    )
    namespace = dict(function.__globals__)
    exec(compile(code, "<upper-root-identity-pivots>", "exec"), namespace)
    return namespace["hierarchical_bound"], original, code


if __name__ == "__main__":
    # The underlying probe binds its own source and both executed function bodies.
    # Bind this driver separately, without modifying the probe's immutable receipt.
    receipt = Path(sys.argv[sys.argv.index("--receipt") + 1])
    manifest = dict(
        variant="lower-factor-reuse-and-direct-upper-solve",
        files={
            str(Path(p).resolve()): hashlib.sha256(Path(p).read_bytes()).hexdigest()
            for p in (__file__, probe.__file__)
        },
        enabled_in_runtime=False,
    )
    with receipt.with_suffix(".driver.json").open("x") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    probe.candidate_function = candidate_function
    probe.main()
