"""Input identity and path confinement belong to the local position store."""

import pytest

from leo.storage.fast_graph_position import FastGraphPositionStore


def test_public_input_updates_produce_new_job_ids(tmp_path):
    folder = tmp_path / "fast-scan-tracking-inputs"
    folder.mkdir()
    source = folder / "scan.json"
    source.write_text("first")
    store = FastGraphPositionStore(tmp_path)
    first = next(store.inputs())
    source.write_text("second")
    second = next(store.inputs())
    assert first["job_id"] != second["job_id"]
    with pytest.raises(ValueError):
        store.verify_input(first)
    with pytest.raises(ValueError):
        store.path("../escape")
