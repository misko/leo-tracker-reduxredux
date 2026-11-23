from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from combined_frontier_run import load_prefetch, verify
from combined_frontier_score import verify_callbacks


def test_private_prefetch_dependency_leaves_ordinary_payload_module_untouched():
    from tools.pipeline_eval.variants.experimental import receiver_ingress
    with load_prefetch()() as stats:
        assert stats.hits == 0
    assert sys.modules[receiver_ingress.__name__] is receiver_ingress


def test_reject_changed_pin_and_speculative_probe_overrun(tmp_path):
    path = tmp_path / "lib"
    path.write_bytes(b"unexpected")
    with pytest.raises(ValueError):
        verify(path, "0"*64)
    ingress = dict(submitted=1, hits=1, hit_bytes=23)
    proof = dict(block_calls=6, block_positions=24, scalar_positions=1, consumed=25)
    verify_callbacks(ingress, proof)
    with pytest.raises(ValueError):
        verify_callbacks(ingress, dict(proof, consumed=24))
