"""Build the opt-in compact receiver with explicit numerical bindings."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

from . import cavity_runtime

V3 = "leo/analysis/localization_v3/"
V4 = "leo/analysis/localization_v4/"
RESEARCH = "leo/analysis/research/"
VARIANTS = "tools/pipeline_eval/variants/"


def replace(source, old, new, *, count=1):
    if source.count(old) != count:
        raise ValueError(f"qualified source anchor changed: {old!r}")
    return source.replace(old, new)


def without(source, start, end=None):
    first = source.index(start)
    last = source.index(end, first + len(start)) if end else len(source)
    return source[:first] + source[last:]


def compact_sources(files):
    """Lower the known compact bindings once when assembling the source distribution."""
    sources = dict(files)
    direct = VARIANTS + "v5_direct_cavity.py"
    source = sources[direct].decode()
    source = without(source, "@contextmanager\ndef numerical_bindings", "def nominal_families")
    for line in (
        "import argparse",
        "from contextlib import contextmanager",
        "from threading import Lock",
        "from tools.pipeline_eval.variants.compact_cavity_optimizer import bounded_secant",
        "_numerical_lock = Lock()",
    ):
        source = replace(source, line + "\n", "")
    source = replace(source, "import project, reclaim", "import reclaim")
    source = replace(source, "bound, stages):", "bound, stages, projector):")
    source = replace(source, 'bound, "previous")', 'bound, "previous", projector.evaluate)')
    source = replace(
        source, 'bound, "genuine_previous")', 'bound, "genuine_previous", projector.evaluate)'
    )
    source = replace(
        source,
        "    with numerical_bindings(projector):\n"
        "        result = infer(prepared, region, bound, "
        '{"native_preparation": perf_counter() - start})',
        "    result = infer(\n"
        "        prepared, region, bound, "
        '{"native_preparation": perf_counter() - start}, projector\n'
        "    )",
    )
    sources[direct] = without(source, "\n\ndef main():").rstrip().encode() + b"\n"
    lifetime = VARIANTS + "v5_direct_lifetime.py"
    sources[lifetime] = (
        without(sources[lifetime].decode(), "\n\ndef main():").rstrip().encode() + b"\n"
    )

    core = VARIANTS + "v5_core.py"
    source = replace(sources[core].decode(), "bound, previous):", "bound, previous, evaluate):")
    sources[core] = replace(
        source, "        bound=bound,", "        bound=bound,\n        evaluate=evaluate,"
    ).encode()

    scan = V3 + "scan.py"
    source = replace(
        sources[scan].decode(),
        "from leo.analysis.research.phase_linear_geometry import (\n"
        "    phase_linear_frequency,\n    prepare_phase_geometry,\n)",
        "from tools.pipeline_eval.variants.orbit_projector "
        "import prepare as prepare_phase_geometry",
    )
    source = replace(source, " import columns_active\n", " import columns_active, project\n")
    source = replace(
        source, "previous_sources=None, bound=None", "previous_sources=None, bound=None, evaluate"
    )
    source = replace(
        source,
        "        self.origin_utc_ns =",
        "        self._evaluate = evaluate\n        self.origin_utc_ns =",
    )
    source = replace(
        source,
        "    def shifted(",
        "    def phase_frequency(self, geometry, *coordinates):\n"
        "        return project(self._evaluate, geometry, coordinates, {})\n\n"
        "    def shifted(",
    )
    sources[scan] = replace(
        source, " = phase_linear_frequency(geometry,", " = self.phase_frequency(geometry,"
    ).encode()
    for module, count in (("discovery", 2), ("family_weighting", 1)):
        name = V3 + module + ".py"
        source = replace(
            sources[name].decode(),
            "from leo.analysis.research.phase_linear_geometry import phase_linear_frequency\n",
            "",
        )
        sources[name] = replace(
            source,
            "phase_linear_frequency(scan.geometry,",
            "scan.phase_frequency(scan.geometry,",
            count=count,
        ).encode()

    position = V3 + "position.py"
    source = replace(
        sources[position].decode(),
        "from leo.analysis.research.continuous_curve_fit import bounded_gauss_newton",
        "from tools.pipeline_eval.variants.compact_cavity_optimizer import bounded_secant",
    )
    sources[position] = replace(source, " = bounded_gauss_newton(", " = bounded_secant(").encode()
    curve = RESEARCH + "continuous_curve_fit.py"
    sources[curve] = (
        without(sources[curve].decode(), "\n\ndef bounded_gauss_newton(").rstrip().encode() + b"\n"
    )
    backend = V4 + "backend.py"
    source = without(sources[backend].decode(), "\n\nclass ProcessBound:")
    for line in (
        "import atexit",
        "import os",
        "from multiprocessing.util import Finalize",
        "from leo.contracts.digests import canonical_digest",
    ):
        source = replace(source, line + "\n", "")
    sources[backend] = source.rstrip().encode() + b"\n"
    for name in sources:
        if name.endswith(".py") and files[name] != sources[name]:
            compile(sources[name], name, "exec")
    return sources


def install(output, *, release=cavity_runtime.RELEASE):
    """Install the cut beside existing profiles with its own freshly bound native manifest."""
    files = cavity_runtime.release_files(release, "phase-release")
    sources = compact_sources(files)
    output = Path(output).resolve()
    if output.is_relative_to("/mnt/qnap01"):
        raise ValueError("the receiver build requires a writable local directory")
    output.mkdir(parents=True, exist_ok=False)
    for name, data in sources.items():
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    (output / "tools/__init__.py").write_text(
        '"""Private receiver modules."""\nPROFILE = "compact-cut"\n'
    )
    (output / "__main__.py").write_bytes(
        Path(cavity_runtime.__file__).with_name("cavity_entry.py").read_bytes()
    )
    command = (
        "import runpy;from pathlib import Path;runpy.run_path('__main__.py')['build'](Path.cwd())"
    )
    subprocess.run(
        [sys.executable, "-IB", "-c", command],
        cwd=output,
        env=dict(os.environ, TMPDIR=str(output)),
        timeout=60,
        check=True,
    )
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="new local installation directory")
    print(install(parser.parse_args().output))
