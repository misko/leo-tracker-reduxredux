from pathlib import Path
import sys
import gzip
import json

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
from combined_frontier_empty import gates
from combined_frontier_run import HERE, load_prefetch, verify
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


@pytest.mark.parametrize("weak_name,empty_name", [
    ("combined-frontier-weak-warm", "combined-frontier-empty"),
    ("combined-frontier-weak-bypass", "combined-frontier-empty-bypass"),
])
def test_two_case_gates_use_matched_input_clocks_for_one_recipe(weak_name, empty_name):
    def read(name):
        return json.loads(gzip.decompress((HERE/"measurements"/f"{name}.json.gz").read_bytes()))
    weak, empty = read(weak_name), read(empty_name)
    assert weak["composition"].get("skip_empty_proof", False) == empty["composition"].get("skip_empty_proof", False)
    times = []
    for receipt, field in ((weak, "clock"), (empty, "timing")):
        cache = [receipt["runs"][a]["cache"] for a in ("stock", "candidate")]
        cache = [c.get("at_launch", c) for c in cache]
        assert all(c["cached_pages"] == c["observed_file_pages"] > 0 for c in cache)
        times.append(tuple(receipt["runs"][a][field]["elapsed_s"] for a in ("stock", "candidate")))
    assert gates(times) == pytest.approx(empty["paired_warm_median_and_sum"])
