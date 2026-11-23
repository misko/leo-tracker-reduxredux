import runpy
from copy import deepcopy
from hashlib import sha256
from pathlib import Path

import pytest

from leo.contracts.fast_standard_analysis import PLOTS

REPORT = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"


def test_successor_verifies_exact_overlay_bytes(tmp_path):
    checked_bytes = runpy.run_path(str(REPORT / "run-successor"))["checked_bytes"]
    source = tmp_path / "overlay.py"
    contents = b"support = True\n"
    source.write_bytes(contents)
    digest = sha256(contents).hexdigest()
    assert checked_bytes(source, digest) == contents

    source.write_bytes(b"support = False\n")
    with pytest.raises(ValueError, match="source changed"):
        checked_bytes(source, digest)


def test_successor_witness_detects_probe_order_arm_png_and_smoke_changes():
    runner = runpy.run_path(str(REPORT / "triage_successor.py"))
    comparison, exact, witnesses = (runner[name] for name in ("comparison", "exact", "witnesses"))
    terminal = dict(arms={"c0": {"latlon": [37.8, -122.4]}, "fitted_c": {"latlon": [37.9, -122.5]}})
    run = dict(
        receipt=dict(terminal_sha256="terminal", decision="complete", region="region"),
        raw_authority="raw", arms=terminal["arms"],
        owners={"c0": "owners", "fitted_c": "owners"},
        scientific_digests={"path": "path", "grid": "grid"},
        artifacts=[{"name": name, "sha256": name} for name in PLOTS],
    )
    native = dict(source=dict(session_id="session", input_manifest_sha256="input",
                              analysis_manifest_sha256="analysis", probes=[
                                  dict(visit_index=i, candidates=[i]) for i in (1, 2)
                              ]))
    baseline = witnesses(run, native)
    positions = {arm: body["latlon"] for arm, body in terminal["arms"].items()}
    smoke = baseline | dict(probes=2, positions=positions)
    equal = comparison(baseline, baseline, [native, native], [terminal, terminal], smoke)
    assert exact(equal)
    assert len(equal["pngs"]) == 8

    changed_native = deepcopy(native)
    changed_native["source"]["probes"].reverse()
    changed = deepcopy(run)
    changed["arms"]["fitted_c"]["latlon"] = None
    changed["artifacts"].pop()
    altered = witnesses(changed, changed_native)
    different = comparison(baseline, altered, [native, changed_native], [terminal, changed["arms"]],
                           smoke | {"raw_authority": "another input"})
    assert not exact(different)
    assert not different["ordered_probes"] and not different["detection_document"]
    assert not different["probe_sha256"] and not different["arms"]
    assert not different["terminal_document"] and not different["pngs"][PLOTS[-1]]
    assert not different["production_witness"]["raw_authority"]
