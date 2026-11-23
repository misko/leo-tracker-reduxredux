from hashlib import sha256
from pathlib import Path
import runpy

import pytest

from leo.contracts.digests import canonical_digest


BOOTSTRAP = runpy.run_path(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3/empty_bootstrap.py"))


def test_every_nonempty_lane_requires_the_ordinary_solver():
    def no_empty_validation(_):
        pytest.fail("Nonempty input belongs to the original solver and validator")

    probes = [{"candidates": []}, {"candidates": [{"candidate_rank": 1, "passed_fractional_margin_gate": False}]}]
    assert BOOTSTRAP["empty_reason"]({"source": {"probes": probes}}, no_empty_validation) is None


def test_empty_with_probes_still_validates_installed_frequency_inputs():
    packet = {"source": {"probes": [{"candidates": []}]}}
    observed = []
    assert BOOTSTRAP["empty_reason"](packet, observed.append) == "no_active_curvature"
    assert observed == [packet]

    def invalid(_):
        raise ValueError("invalid clock support")

    with pytest.raises(ValueError, match="invalid clock support"):
        BOOTSTRAP["empty_reason"](packet, invalid)
    assert BOOTSTRAP["empty_reason"]({"source": {"probes": []}}, invalid) == "no valid receiver windows in the sealed recording"


def test_handoff_requires_original_receiver_inventory_and_sealed_rows():
    digest, inventory, session = "ab" * 32, "inventory", "session"
    probes = [{"candidates": []}]
    native = {
        "source": {"session_id": session, "input_manifest_sha256": inventory, "qualified": True,
                   "raw_recording_authority_digest": "raw", "probes": probes,
                   "analysis_manifest_sha256": canonical_digest(["cancellation", "raw", digest, probes])},
        "provenance": {"detector_sha256": "sha256:" + digest},
    }
    expected = canonical_digest(native)
    bind = BOOTSTRAP["bind_native"]
    bind(native, session, inventory, digest, expected=expected)
    with pytest.raises(ValueError, match="raw authority"):
        bind(native, session, inventory + "changed", digest, expected=expected)
    with pytest.raises(ValueError, match="raw authority"):
        bind(native, session, inventory, "cd" * 32, expected=expected)
    native["other"] = "changed"
    with pytest.raises(ValueError, match="raw authority"):
        bind(native, session, inventory, digest, expected=expected)
    probes[0]["candidates"] = [{"candidate_rank": 0}]
    with pytest.raises(ValueError, match="raw authority"):
        bind(native, session, inventory, digest)


def test_reviewed_extraction_checks_bytes_and_skips_unneeded_top_level_setup(tmp_path):
    source = b'def useful(x):\n    return x + 1\nraise RuntimeError("imported an unused dependency")\n'
    path = tmp_path / "reviewed.py"
    path.write_bytes(source)
    pin = sha256(source).hexdigest()
    scope = {}
    BOOTSTRAP["load_definitions"](BOOTSTRAP["checked"](path, pin), path, ("useful",), scope)
    assert scope["useful"](9) == 10
    path.write_bytes(source + b"\n")
    with pytest.raises(ValueError, match="Unreviewed bootstrap input"):
        BOOTSTRAP["checked"](path, pin)
