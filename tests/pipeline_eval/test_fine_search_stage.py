import csv
from collections import Counter

import pytest

from tools.pipeline_eval.qualification import fine_search_stage, receiver_core_pack
from tools.pipeline_eval.qualification.capture_runtime import read


def test_fine_search_stage_export_is_reproducible_and_discoverable(tmp_path):
    report = fine_search_stage.REPORT
    lock = fine_search_stage.MEASUREMENT_SEAL
    originals = (report / lock).read_bytes()
    (tmp_path / lock).write_bytes(originals)
    for name in read(report / lock)["files"]:
        (tmp_path / name).write_bytes((report / name).read_bytes())

    fine_search_stage.export(tmp_path)
    ((panel, descriptor),) = receiver_core_pack.stage_specs(tmp_path)
    assert panel.id == "pruned-fine-cfo-search"
    assert descriptor.name == fine_search_stage.DESCRIPTOR
    assert (tmp_path / lock).read_bytes() == originals
    for name in (panel.source_csv, "stage-summary.csv", panel.seal, descriptor.name):
        assert (tmp_path / name).read_bytes() == (report / name).read_bytes()

    with (tmp_path / panel.source_csv).open() as stream:
        observed = list(csv.DictReader(stream))
    counts = Counter((r["stage"], r["mode"]) for r in observed)
    assert counts == {
        (stage, mode): count
        for stage, count in (("complete_detector", 80), ("fine_cfo_scoring", 16))
        for mode in ("row_wise", "pruned")
    }
    assert all(bool(r["wall_ms"]) == (r["stage"] == "complete_detector") for r in observed)

    (tmp_path / panel.source_csv).write_text("tampered\n")
    with pytest.raises(ValueError, match="assets differ from the sealed stage results"):
        receiver_core_pack.add_authored_stage(
            tmp_path, tmp_path / "exports", None, panel, descriptor
        )
