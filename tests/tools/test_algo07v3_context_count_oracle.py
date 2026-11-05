import json
from pathlib import Path

import pytest
from algo07v3_context_count_oracle import inventory_path


def test_each_original_worker_inventory_argument_is_resolved_explicitly(tmp_path):
    assert (
        inventory_path("target-1-inclusion", ["--inventory", str(tmp_path / "inv")])
        == tmp_path / "inv"
    )
    (tmp_path / "protocol.json").write_text(json.dumps({"job": {"job_id": "case"}}))
    assert inventory_path("target-1-audit", ["--trial", str(tmp_path), "--study", "/study"]) == (
        Path("/study/all-large-track-recovery/case/inventory.json")
    )


@pytest.mark.parametrize(
    "name", ["inactive_fragment_sources", "graph_bundle_sources", "measurement_refinements"]
)
def test_unqualified_context_modifications_are_rejected(tmp_path, name):
    (tmp_path / "protocol.json").write_text(
        json.dumps({"job": {"job_id": "case"}, name: ["extra"]})
    )
    with pytest.raises(ValueError, match="separate qualification"):
        inventory_path("target-1-audit", ["--trial", str(tmp_path), "--study", "/study"])
