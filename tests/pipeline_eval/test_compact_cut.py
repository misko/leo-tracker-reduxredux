import ast
import subprocess
import sys
from pathlib import Path

import pytest

from tools.pipeline_eval import cavity_runtime, compact_cut, whole_iq


@pytest.fixture(scope="module")
def donor():
    return cavity_runtime.release_files(cavity_runtime.RELEASE, "phase-release")


@pytest.fixture(scope="module")
def receiver(tmp_path_factory):
    return compact_cut.install(tmp_path_factory.mktemp("compact-cut") / "receiver")


def test_released_sources_keep_every_scientific_path(donor):
    cut = compact_cut.compact_sources(donor)
    assert cut.keys() == donor.keys()
    changed = {name for name, data in cut.items() if data != donor[name]}
    assert changed == {
        compact_cut.V3 + name + ".py"
        for name in ("scan", "position", "family_weighting", "discovery")
    } | {
        compact_cut.V4 + "backend.py",
        compact_cut.RESEARCH + "continuous_curve_fit.py",
        *(
            compact_cut.VARIANTS + name + ".py"
            for name in ("v5_core", "v5_direct_cavity", "v5_direct_lifetime")
        ),
    }
    for name in changed:
        old, new = (ast.parse(s[name]) for s in (donor, cut))
        assert not any(
            isinstance(node, ast.Name) and node.id == "setattr" for node in ast.walk(new)
        )
        assert len(ast.dump(new)) <= len(ast.dump(old)) or name in {
            compact_cut.V3 + "scan.py",
            compact_cut.VARIANTS + "v5_core.py",
        }
    assert b"phase_linear_frequency" in cut[compact_cut.V3 + "conservative_recovery.py"]
    assert b"with projection_columns():" in cut[compact_cut.VARIANTS + "v5_core.py"]


def test_installer_rejects_changed_source_anchor(donor):
    changed = dict(donor)
    source = compact_cut.V3 + "position.py"
    changed[source] = changed[source].replace(b"= bounded_gauss_newton(", b"= another_fit(")
    with pytest.raises(ValueError, match="qualified source anchor"):
        compact_cut.compact_sources(changed)


def test_out_of_tree_receiver_keeps_two_live_projectors_separate(receiver):
    script = """
import runpy
from pathlib import Path

root = Path.cwd()
entry = runpy.run_path('__main__.py')
entry['activate'](root)
from leo.analysis.localization_v3.scan import ScanLikelihood
from leo.analysis.localization_v3 import position
from leo.analysis.localization_v3.conservative_recovery import phase_linear_frequency
from leo.analysis.research.phase_linear_geometry import phase_linear_frequency as early
from leo.analysis.localization_v4.backend import read_manifest, validate_manifest
from tools.pipeline_eval.variants.compact_cavity_optimizer import bounded_secant
from tools.pipeline_eval.variants.v5_direct_lifetime import columns_active, projection_columns
from tools.pipeline_eval.variants.orbit_projector import prepare

import numpy as np

assert position.bounded_secant is bounded_secant
assert phase_linear_frequency is early
def create(offset):
    scan = ScanLikelihood.__new__(ScanLikelihood)
    scan._evaluate = lambda stencil, x, y: (x + offset, y + offset, stencil)
    return scan
a, b = create(1), create(2)
sentinel = object()
assert a.phase_frequency(sentinel, 10, 20) == (11, 21, sentinel)
assert b.phase_frequency(sentinel, 10, 20) == (12, 22, sentinel)
grid = prepare({
    'time_s': np.asarray([-1., 1.]),
    'position_km': np.ones((1, 2, 3)) * 7000,
    'velocity_km_s': np.ones((1, 2, 3)),
}, np.zeros(1))
with projection_columns():
    x = a.phase_frequency(grid, 10, 20)
    y = b.phase_frequency(grid, 10, 20)
    assert x[0].source is x[1].source and x[1].source is x[2].source
    assert x[0].source is not y[0].source
assert not columns_active.get()
entry['verify_project_modules'](root)
validate_manifest(read_manifest(root/'native/manifest.json'), check_provider=True)
"""
    # Project paths are resolved from the installed tree in an isolated interpreter.
    subprocess.run([sys.executable, "-IB", "-c", script], cwd=receiver, check=True, timeout=30)
    assert whole_iq.native_sources(receiver)
    help_text = subprocess.check_output(
        [sys.executable, "-IB", str(receiver), "--help"], cwd=Path.home(), text=True, timeout=15
    )
    assert "--native-sha256" in help_text and "--width-km" in help_text
