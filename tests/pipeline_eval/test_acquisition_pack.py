import csv
import io
from zipfile import ZipFile

import pytest

from tools.pipeline_eval.qualification import acquisition_pack as pack


def test_zip_has_portable_links_unique_pngs_and_reproducible_bytes(tmp_path):
    stages = tmp_path / "stage-charts"
    stages.mkdir()
    (stages / "stage-evidence.pdf").write_bytes(b"stage PDF")
    (tmp_path / "present.png").write_bytes(b"img")
    row = pack.index.Row(
        "fit",
        "fit",
        "Fit",
        "Roof",
        "GLRT to fix",
        "Position",
        "c0",
        "Chart ready",
        "1 recording",
        chart="present.png",
    )
    data = b"figure,arm\nfit,c0\n"
    blob = pack.archive(tmp_path, [row], data)
    assert blob == pack.archive(tmp_path, [row], data)
    with ZipFile(io.BytesIO(blob)) as z:
        assert z.testzip() is None and z.read("positions.csv") == data
        assert z.read("c0/fit.png") == b"img"
        inventory = next(csv.DictReader(io.StringIO(z.read("chart-inventory.csv").decode())))
        assert inventory["chart"] == "c0/fit.png" and inventory["report"] == ""
        assert b'href="c0/fit.png"' in z.read("index.html")
    with pytest.raises(ValueError, match="duplicate"):
        pack.archive(tmp_path, [row, row], data)


def test_observations_require_one_source_table_per_panel_and_keep_timeout(tmp_path):
    sample = tmp_path / "scores.csv"
    sample.write_text("figure,arm,decision,error_km\nfit,c0,timed_out,\nextra,c0,published,17\n")
    panels = {("c0", "fit")}
    assert pack.observations(panels, [sample]).decode().splitlines()[-1] == "fit,c0,timed_out,"
    with pytest.raises(ValueError, match="more than one"):
        pack.observations(panels, [sample, sample])
    with pytest.raises(ValueError, match="missing"):
        pack.observations({("fitted_c", "fit")}, [sample])
