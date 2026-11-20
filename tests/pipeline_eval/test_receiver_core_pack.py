import csv
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlparse
from zipfile import ZipFile

import pytest
from matplotlib.backends.backend_pdf import PdfPages
from PIL import Image

from tools.pipeline_eval.qualification import receiver_core_pack as pack


def test_stage_uses_exact_measured_values_and_all_recording_rosters():
    real = pack.ROOT
    lanczos, vnni, stride, carry, envelope, proxy, arm = (
        pack.screened(real, False),
        pack.screened(real, True),
        pack.stride_host(real),
        pack.carry(real),
        pack.envelope(real),
        pack.proxy(real),
        pack.stride_arm(real),
    )
    assert len({p.id for p in (lanczos, vnni, stride, carry, envelope, proxy, arm)}) == 7
    for p in (lanczos, vnni, stride, carry, envelope, proxy, arm):
        assert len(p.plots) == 2
        assert p.sources and all(len(v) == 64 for v in p.sources.values())
        assert all(r["unit"] for r in p.rows)
        assert all("position" not in r["metric"] for r in p.rows)
    assert set(lanczos.plots[0][2]) == {"DS26-0036", "DS29-0174"}
    assert vnni.plots[0][2] == ["DS29-0174"]
    assert len({r["recording"] for r in carry.rows if r["metric"] == "processed_probe"}) == 8
    assert envelope.plots[0][3] == [(13, 13), (16, 16)]
    assert sum(candidate for _, candidate in proxy.plots[0][3]) == 29
    assert any(r["value"] == "invalid_capture" for r in arm.rows)


def test_stage_loader_rejects_data_changed_after_sealing(tmp_path):
    data = tmp_path / "scores.json"
    data.write_text('{"cpu_ms": 41}')
    lock = tmp_path / "prediction-lock.json"
    lock.write_text(
        json.dumps({"files": {data.name: hashlib.sha256(data.read_bytes()).hexdigest()}})
    )
    assert pack.sealed(tmp_path, lock.name, (data.name,))[0] == {data.name: {"cpu_ms": 41}}
    data.write_text('{"cpu_ms": 42}')
    with pytest.raises(ValueError, match="unsealed stage source"):
        pack.sealed(tmp_path, lock.name, (data.name,))


def test_portable_pack_keeps_stage_and_position_tables_separate(tmp_path, monkeypatch):
    def stages(root, destination):
        assert root == destination
        folder = root / "stage-charts"
        folder.mkdir(exist_ok=True)
        for name in (
            "detector.png",
            "detector.csv",
            "measurements.csv",
            "manifest.json",
            "README.md",
            pack.stage.BOOK,
        ):
            (folder / name).write_text(name)
        return [
            pack.index.Row(
                "detector",
                "detector",
                "Detector",
                "Pair",
                "IQ to detector",
                "Stage",
                "stage",
                "Chart ready",
                "2 visits",
                chart="stage-charts/detector.png",
                evidence="stage-charts/detector.csv",
                report="detector/README.md",
            )
        ], [dict(csv="detector.csv")]

    def positions(root, destination, models):
        assert root == destination and models is None
        charts = root / "charts"
        charts.mkdir(exist_ok=True)
        (charts / "manifest.json").write_text("[]")
        (charts / "index.html").write_text('<a href="../index.html">Index</a>')
        rows, specs = [], []
        for arm in pack.ARMS:
            folder = charts / arm
            folder.mkdir(exist_ok=True)
            (folder / "fix.png").write_bytes(b"png")
            (folder / "position.pdf").write_bytes(b"pdf")
            (folder / "position.csv").write_text(
                f"arm,figure,decision,error_km\n{arm},fix,timed_out,\n"
            )
            rows.append(
                pack.index.Row(
                    "fix",
                    "fix",
                    "Fit",
                    "Roof",
                    "IQ to fit",
                    "Position",
                    arm,
                    "Chart ready",
                    "1 recording",
                    chart=f"charts/{arm}/fix.png",
                    evidence="fit/seal.json",
                )
            )
            specs.append(dict(arm=arm, pdf=f"{arm}/position.pdf", csv=f"{arm}/position.csv"))
        return rows, specs

    monkeypatch.setattr(pack, "stage_book", stages)
    monkeypatch.setattr(pack, "position_book", positions)
    board = tmp_path / "board-replay"
    board.mkdir()
    (board / "README.md").write_text("Authentication audit")
    assert len(pack.build(tmp_path)) == 3
    assert 'href="board-replay/README.md"' in (tmp_path / "index.html").read_text()
    original = (tmp_path / pack.ZIP).read_bytes()
    pack.build(tmp_path)
    assert original == (tmp_path / pack.ZIP).read_bytes()
    with ZipFile(io.BytesIO(original)) as z:
        assert z.testzip() is None
        assert all(not name.startswith("board-replay/") for name in z.namelist())
        digests = json.loads(z.read("artifact-sha256.json"))["files"]
        assert set(digests) == set(z.namelist()) - {"artifact-sha256.json"}
        assert all(hashlib.sha256(z.read(name)).hexdigest() == h for name, h in digests.items())
        rows = list(csv.DictReader(io.StringIO(z.read("chart-inventory.csv").decode())))
        assert [r["evidence"] for r in rows] == [
            "positions.csv",
            "positions.csv",
            "stage-charts/detector.csv",
        ]
        assert all(r["report"] == "" and r["chart"] in z.namelist() for r in rows)
        assert b"timed_out," in z.read("positions.csv")
        paths = z.read("index.html").decode().split('href="')[1:]
        assert all(
            unquote(urlparse(item.split('"')[0]).path) in z.namelist()
            for item in paths
            if not item.startswith("#")
        )
    assert all(
        hashlib.sha256((tmp_path / name).read_bytes()).hexdigest() == digest
        for name, digest in json.loads((tmp_path / "pack-lock.json").read_bytes())["files"].items()
    )
    with pytest.raises(ValueError, match="ZIP path escapes"):
        pack.portable_zip({str(Path("../invalid")): b"invalid"})


@pytest.mark.parametrize("panel", pack.AUTHORED_STAGES, ids=lambda panel: panel.id)
def test_authored_stage_appends_a_dedicated_pdf_page_and_checks_its_data(tmp_path, panel):
    source = tmp_path / panel.id
    source.mkdir()
    csv_name = panel.source_csv or f"{panel.id}.csv"
    (source / f"{panel.id}.pdf").write_bytes(b"original PDF")
    (source / csv_name).write_bytes(b"recording,error_samples\nDS26-0036,71\n")
    Image.new("RGB", (100, 80), "white").save(source / f"{panel.id}.png")
    lock = source / panel.seal
    lock.write_text(json.dumps(dict(files={p.name: pack.stage.sha(p) for p in source.iterdir()})))
    page = io.BytesIO()
    with PdfPages(page) as book:
        row, manifest = pack.add_authored_stage(tmp_path, tmp_path / "stage-charts", book, panel)
        assert book.get_pagecount() == 1
    assert row.arm == "stage" and row.panel_id == panel.id
    assert page.getvalue().startswith(b"%PDF")
    assert manifest["csv"] == f"{panel.id}.csv"
    assert (tmp_path / row.evidence).read_bytes() == (source / csv_name).read_bytes()
    assert manifest["sources"][f"{panel.id}/{csv_name}"] == pack.stage.sha(source / csv_name)
    (source / csv_name).write_bytes(b"overwritten")
    with pytest.raises(ValueError, match=f"{panel.id} assets differ"):
        pack.add_authored_stage(tmp_path, tmp_path / "stage-charts", None, panel)
    table = source / csv_name
    table.write_text("recording,error_samples\n")
    receipt = json.loads(lock.read_text())
    receipt["files"][csv_name] = pack.stage.sha(table)
    lock.write_text(json.dumps(receipt))
    with pytest.raises(ValueError, match=f"{panel.id} stage CSV has no measured rows"):
        pack.add_authored_stage(tmp_path, tmp_path / "stage-charts", None, panel)


def test_unsealed_stages_and_board_access_notes_are_not_published_as_measurements(tmp_path):
    for name in ("causal-track-scout", "hinted-glrt", "range-epoch", "board-replay"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "README.md").write_text("Draft operational notes")
    assert pack.stage_book(tmp_path) == ([], [])


def test_scoped_stage_descriptor_keeps_original_chart_and_creates_no_position_book(tmp_path):
    root = tmp_path / "track-recovery"
    folder = root / "turn-analysis" / "actual-stage"
    folder.mkdir(parents=True)
    image = folder / "turn-support.png"
    table = folder / "measurements.csv"
    Image.new("RGB", (100, 80), "#325368").save(image)
    table.write_text("capture,held_arcs,count_unit\ncapture-1,0,arcs\n")
    seal = folder / "measurement-lock.json"
    seal.write_text(json.dumps({"files": {p.name: pack.stage.sha(p) for p in (image, table)}}))
    descriptor = folder / pack.STAGE_SPEC
    source = dict(
        version=1,
        id="turn-support",
        title="Measured support",
        sample="One capture",
        boundary="Saved arc → held-turn gate",
        note="No held turn was found.",
        seal=seal.name,
        image=image.name,
        csv=table.name,
    )
    descriptor.write_text(json.dumps(source))
    pending = root / "pending-stage"
    pending.mkdir()
    (pending / pack.STAGE_SPEC).write_text(json.dumps(source | {"id": "pending-stage"}))
    rows = pack.build(root)
    assert len(rows) == 1 and rows[0].arm == "stage"
    with ZipFile(root / pack.ZIP) as z:
        assert z.read("stage-charts/turn-support.png") == image.read_bytes()
        assert z.read("stage-charts/turn-support.csv") == table.read_bytes()
        assert "stage-charts/turn-support.pdf" not in z.namelist()
        assert "positions.csv" not in z.namelist()
        assert b"Track recovery measurements" in z.read("index.html")
        assert b"Position results" not in z.read("index.html")
        packed = json.loads(z.read("stage-charts/manifest.json"))["pages"][0]
        assert packed["sources"][str(descriptor.relative_to(root))] == pack.stage.sha(descriptor)
    descriptor.write_text(json.dumps(source | {"image": "../turn-support.png"}))
    with pytest.raises(ValueError, match="within"):
        pack.stage_book(root)


def test_scoped_position_book_skips_explicitly_unattempted_stages(tmp_path, monkeypatch):
    rows = {"case": {"result": {"metrics": {"position_attempted": False}}}}
    stage = SimpleNamespace(scope="transfer", predictions={"candidate": rows}, version=1)
    monkeypatch.setattr(pack.position, "available", lambda root: True)
    monkeypatch.setattr(pack.position, "charts", lambda **kwargs: [stage])
    assert pack.position_book(tmp_path / "track-recovery") == ([], [])
    assert not (tmp_path / "track-recovery/charts").exists()
    rows["case"]["result"]["metrics"] = {}
    assert pack.position_attempted(stage)


def test_terminal_position_gate_counts_in_both_calibration_arms():
    result = {
        "status": "withheld",
        "reason": "No consistent in-tile orbit set",
        "metrics": {"position_attempted": False, "terminal_position_decision": True},
        "arms": {arm: {"latlon": None, "forced_latlon": None} for arm in pack.ARMS},
    }
    chart = SimpleNamespace(
        scope="transfer", predictions={"candidate": {"case": {"result": result}}}
    )
    assert pack.position_attempted(chart)
    for arm in pack.ARMS:
        counts = pack.index.outcome([result], arm)
        assert counts["withheld"] == 1
        assert all(value == 0 for key, value in counts.items() if key != "withheld")


def test_scheduled_failure_before_refinement_remains_pack_eligible():
    result = {"status": "failed", "metrics": {"position_attempted": False}}
    chart = SimpleNamespace(
        scope="roof", predictions={"one": {"case": {"result": result}}}, version=2
    )
    assert pack.position_attempted(chart)
    chart.version = 1
    assert not pack.position_attempted(chart)
    for arm in pack.ARMS:
        assert pack.index.outcome([result], arm)["failed"] == 1
