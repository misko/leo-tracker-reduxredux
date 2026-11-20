"""Install a source-verified accepted-endpoint overlay on the public compact receiver."""

from pathlib import Path

from .. import cavity_runtime
from ..variants import compact_endpoint
from .compact_catalogue_build import replace
from .full_receiver_comparison import sha

PREFIX = "tools/pipeline_eval/variants/"
PHYSICS = "leo/analysis/localization_v3/"
COMPONENT = PREFIX + "compact_endpoint.py"
ENTRY = PREFIX + "v5_direct_cavity.py"
OPTIMIZER = PREFIX + "compact_cavity_optimizer.py"


def stage(values, enabled):
    def edit(name, transform):
        values[name] = transform(values[name].decode()).encode()

    def entry(source):
        source = replace(
            source,
            "    with numerical_bindings(projector):",
            "    from .compact_endpoint import receipt, reset\n\n"
            f"    reset({enabled!r})\n    with numerical_bindings(projector):",
        )
        return replace(
            source,
            '    result["metrics"]["compact_projections"] = projector.calls',
            '    result["metrics"]["compact_projections"] = projector.calls\n'
            '    result["metrics"]["endpoint_reuse"] = receipt()',
        )

    def optimizer(source):
        for old, new in (
            ("*, iterations=24, step=1e-3):", "*, iterations=24, step=1e-3, on_accept=None):"),
            (
                "    r = residual(x)\n",
                "    r = residual(x)\n    if on_accept is not None:\n        on_accept(x)\n",
            ),
            (
                "            x, r, score = proposal, rr, candidate\n",
                "            x, r, score = proposal, rr, candidate\n"
                "            if on_accept is not None:\n                on_accept(x)\n",
            ),
        ):
            source = replace(source, old, new)
        return source

    def position(source):
        source = replace(
            source,
            "    result = bounded_gauss_newton(problem.residual, start, problem.lower, "
            "problem.upper,\n"
            "                                 iterations=iterations)\n"
            "    calculated = problem.calculate(result['parameters'])",
            "    result = optimize(problem, bounded_gauss_newton, start, iterations)\n"
            "    calculated = endpoint(problem, result['parameters'])",
        )
        return replace(
            source, "        result = self.calculate(x)\n", "        result = endpoint(self, x)\n"
        )

    def marginal(source):
        for method in ("state", "conditional_frequency", "diagnostics"):
            if method == "conditional_frequency":
                prefix = (
                    "    def conditional_frequency(self, x):\n"
                    '        """Reference-Hz orbit prediction, '
                    'excluding hardware and curve constants."""\n'
                )
            else:
                prefix = f"    def {method}(self, x):\n"
            source = replace(
                source,
                prefix + "        result = self.calculate(x)",
                prefix + "        result = endpoint(self, x)",
            )
        return source

    def reporting(name, old, new, *, count=1):
        def convert(source):
            if source.count(old) != count:
                raise ValueError("normal reporting anchor differs from the sealed receiver")
            return source.replace(old, new)

        with_endpoint(name, convert)

    def with_endpoint(name, transform, imports="endpoint"):
        def convert(source):
            source = transform(source)
            return replace(
                source,
                "import numpy as np\n",
                "import numpy as np\n\n"
                f"from tools.pipeline_eval.variants.compact_endpoint import {imports}\n",
            )

        edit(PHYSICS + name, convert)

    edit(ENTRY, entry)
    edit(OPTIMIZER, optimizer)
    with_endpoint("position.py", position, "endpoint, optimize")
    with_endpoint("marginal.py", marginal)
    reporting(
        "retained_position.py", "    c = p.calculate(anchor)\n", "    c = endpoint(p, anchor)\n"
    )
    reporting(
        "history_position.py", "    c = p.calculate(anchor)\n", "    c = endpoint(p, anchor)\n"
    )
    reporting("predictive_linear.py", "    c = p.calculate(x)\n", "    c = endpoint(p, x)\n")
    reporting(
        "conservative_recovery.py", "    result = p.calculate(x)\n", "    result = endpoint(p, x)\n"
    )
    reporting(
        "acceptance.py", "    result = p.calculate(x)\n", "    result = endpoint(p, x)\n", count=2
    )
    edit(
        PHYSICS + "event_position.py",
        lambda source: replace(
            source,
            "    p.calculate = lambda x: calculate(tuple(x))",
            "    p.calculate = lambda x: calculate(tuple(x))\n    p._has_fit_cache = True",
        ),
    )
    values[COMPONENT] = Path(compact_endpoint.__file__).read_bytes()
    return values


def install(out, *, enabled=True):
    originals = cavity_runtime.release_files(cavity_runtime.RELEASE, "phase-release")
    files = stage(dict(originals), enabled)
    cavity_runtime.install(out, profile="phase-release")
    for name, payload in files.items():
        path = out / name
        if name in originals and path.read_bytes() != originals[name]:
            raise ValueError("portable source differs from the verified base release")
        if payload != originals.get(name):
            compile(payload, str(path), "exec")
            path.write_bytes(payload)
    return {name: sha(out / name) for name in files}


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    parser.add_argument("--stock", action="store_true")
    args = parser.parse_args()
    install(args.path, enabled=not args.stock)
