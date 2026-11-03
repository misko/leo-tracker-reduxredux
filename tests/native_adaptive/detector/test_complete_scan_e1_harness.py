import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "reports/2026_09_30_native_adaptive_deployment/ds9/complete-scan-e1/run.py"


def load_harness():
    spec = importlib.util.spec_from_file_location("complete_scan_e1", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_source_authority_rejects_conflicting_window(tmp_path):
    module = load_harness()
    source = {"visit": 7, "receiver": 1, "probe_index": 0, "window_counter": 10}
    changed = {**source, "window_counter": 11}
    path = tmp_path / "authority.jsonl"
    path.write_text(
        "\n".join(
            (
                f'{{"source":{module.json.dumps(source)}}}',
                f'{{"source":{module.json.dumps(changed)}}}',
            )
        )
        + "\n"
    )
    with pytest.raises(ValueError, match="conflicting source authority"):
        module.load_sources(path)


def test_incomplete_fractional_record_is_explicitly_unavailable():
    module = load_harness()
    source = {
        "rate": 7_500_000,
        "anchor_counter": 1,
        "anchor_utc_ns": 2,
        "generation": 3,
        "visit": 4,
        "window_counter": 5,
        "probe_index": 0,
        "receiver": 1,
        "channel": 2,
        "upper_edge": False,
        "actual_rf_hz": 10_960_000_000.0,
        "utc_bracket_width_ns": 6,
        "input_digest": "sha256:" + "1" * 64,
        "continuity_qualified": True,
    }
    candidate = {
        "epoch": 9,
        "fractional_epoch": {
            "status": "unbracketed",
            "offset_samples": None,
            "tracking_cfo_hz": None,
            "exact_score": None,
            "control_score": None,
            "margin": None,
        },
    }
    fields = module.project_record(source, "sha256:" + "2" * 64, 0, candidate).split("\t")
    assert fields[-1] == "0"
    assert fields[-6:-1] == ["0", "0", "0", "0", "0"]
