import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

PATH = Path(__file__).parents[2] / "tools/research/report_five_block_position.py"
SPEC = importlib.util.spec_from_file_location("report_five_block_position", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_distance_is_zero_and_symmetric():
    assert MODULE.distance_km(10, 20, 10, 20) == 0
    assert MODULE.distance_km(10, 20, 11, 21) == pytest.approx(MODULE.distance_km(11, 21, 10, 20))


def test_load_sealed_rejects_mutated_result(tmp_path):
    result = {"position_truth_used": False, "complete": True, "fits": [{"converged": True}]}
    payload = json.dumps(result).encode()
    (tmp_path / "result.json").write_bytes(payload)
    (tmp_path / "result.sha256").write_text(hashlib.sha256(payload).hexdigest())
    (tmp_path / "refinement-seal.json").write_text(
        json.dumps(
            {
                "result_digest": MODULE.digest(tmp_path / "result.json"),
                "all_fits_converged": True,
            }
        )
    )
    assert MODULE.load_sealed(tmp_path) == result
    (tmp_path / "result.json").write_text('{"position_truth_used": true}')
    with pytest.raises(ValueError, match="unsealed"):
        MODULE.load_sealed(tmp_path)
