import csv
import gzip
import json
from hashlib import sha256

import pytest

from tools.pipeline_eval.qualification import acquisition_index as index


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def prediction(case, status, c0=None, fitted=None, forced=None):
    return dict(
        id=case,
        method="scout",
        result=dict(
            status=status,
            metrics={},
            arms=dict(
                c0=dict(latlon=c0, forced_latlon=forced),
                fitted_c=dict(latlon=fitted, forced_latlon=forced),
            ),
        ),
    )


def sealed_study(folder):
    data = [
        prediction("A", "ok", fitted=[5, 6], forced=[5, 6]),
        prediction("B", "withheld", forced=[3, 4]),
        prediction("C", "failed"),
        prediction("D", "timed_out"),
    ]
    control = [
        dict(prediction(d["id"], "timed_out" if d["id"] == "B" else "withheld"), method="stock")
        for d in data
    ]
    raw = gzip.compress(b"\n".join(json.dumps(d).encode() for d in data + control))
    (folder / "positions.jsonl.gz").write_bytes(raw)
    dump(
        folder / "seal.json",
        dict(
            cases=[d["id"] for d in data],
            files={"positions.jsonl.gz": sha256(raw).hexdigest()},
        ),
    )
    dump(
        folder / "figures.json",
        dict(
            charts=[
                dict(
                    id="scout-centers-all",
                    title="Sixteen proposals",
                    scope="roof",
                    seal="seal.json",
                    caption="Full IQ to position",
                    cases="sealed",
                    series=[
                        dict(key="one", value="scout", file="positions.jsonl.gz"),
                        dict(key="stock", value="stock", file="positions.jsonl.gz"),
                    ],
                )
            ]
        ),
    )


def test_index_replaces_pending_with_actual_both_arm_evidence(tmp_path):
    root = tmp_path / "acquisition-support"
    scout, atlas = root / "scout-full", tmp_path / "atlas"
    scout.mkdir(parents=True)
    first = index.build(root, atlas, tmp_path)
    assert [r.scheduled for r in first if r.panel_id == "scout-full"] == [8, 8]
    sealed_study(scout)
    local_gallery = scout / "charts"
    global_gallery = root / "charts"
    for gallery, arm in ((local_gallery, "fitted_c"), (global_gallery, "fitted_c")):
        dump(
            gallery / "manifest.json",
            [
                dict(
                    id="scout-centers-all",
                    arm=arm,
                    image=f"{arm}/scout-centers-all.png",
                )
            ],
        )
        image = gallery / arm / "scout-centers-all.png"
        image.parent.mkdir()
        image.write_bytes(b"fixture figure")
    rows = index.build(root, atlas, tmp_path)
    assert not any(r.panel_id == "scout-full" for r in rows)
    fitting, zero = [r for r in rows if r.panel_id == "scout-centers-all"]
    assert fitting.state == "Chart ready"
    assert fitting.chart == "charts/fitted_c/scout-centers-all.png"
    assert fitting.published == 1 and zero.published == 0
    assert fitting.withheld == 1 and zero.withheld == 2
    assert fitting.forced_available == zero.forced_available == 2
    assert fitting.failed == fitting.timed_out == zero.failed == zero.timed_out == 1
    assert zero.state == "Sealed replay · chart pending"
    assert zero.chart == "" and "D timed_out" in zero.terminal_exceptions
    assert "B timed_out" in fitting.comparison_failures
    text = (root / "index.html").read_text()
    assert "charts/fitted_c/scout-centers-all.png" in text
    assert "charts/c0/scout-centers-all.png" not in text
    assert "modification-charts.zip" not in text
    (root / "modification-charts.zip").write_bytes(b"fixture bundle")
    index.build(root, atlas, tmp_path)
    assert 'href="modification-charts.zip"' in (root / "index.html").read_text()
    with (root / "chart-inventory.csv").open() as stream:
        entries = [r for r in csv.DictReader(stream) if r["panel_id"] == "scout-centers-all"]
    assert [r["published"] for r in entries] == ["1", "0"]


def test_source_or_roster_mismatch_does_not_invent_counts(tmp_path):
    scout = tmp_path / "scout-full"
    scout.mkdir()
    sealed_study(scout)
    (scout / "positions.jsonl.gz").write_bytes(b"edited after sealing")
    positions = [
        r
        for r in index.inventory(tmp_path, tmp_path / "atlas", tmp_path)
        if r.panel_id == "scout-centers-all"
    ]
    assert all(r.state == "Unverified" and r.scheduled is None for r in positions)
    assert all(r.published is None and not r.chart for r in positions)


def test_long_terminal_reason_wraps_inside_the_arm_status_and_remains_readable():
    reason = "calibration_unavailable_with_independent_track_intercepts" * 2 + " <arm>"
    row = index.Row(
        "site",
        "held-site",
        "Held site",
        "One site",
        "CFO to position",
        "Position",
        "fitted_c",
        "Chart ready",
        "Two visits",
        terminal_exceptions=reason,
    )
    html = index.page([row], {})
    assert "Each stage chart identifies the operation measured." in html
    assert "li>span{overflow-wrap:anywhere}" in html
    assert f"<br>{reason.replace('<arm>', '&lt;arm&gt;')}</span></li>" in html


def test_stage_chart_requires_real_image_and_authenticated_sources(tmp_path):
    root = tmp_path / "acquisition-support"
    stage = root / "stage-charts"
    receipt = root / "folded-bank" / "receipt.json"
    dump(receipt, {"evidence": 1})
    digest = sha256(receipt.read_bytes()).hexdigest()
    dump(
        stage / "manifest.json",
        dict(
            version=1,
            pages=[
                dict(
                    id="folded-bank",
                    title="Shared bank",
                    image="folded-bank.png",
                    sources={receipt.relative_to(tmp_path).as_posix(): digest},
                )
            ],
        ),
    )
    image = stage / "folded-bank.png"
    image.write_bytes(b"fixture figure")
    first = next(r for r in index.stages(root, tmp_path) if r.panel_id == "folded-bank")
    assert first.chart == "stage-charts/folded-bank.png"
    assert first.arm == "stage" and first.published is None and first.withheld is None
    dump(receipt, {"edited": True})
    second = next(r for r in index.stages(root, tmp_path) if r.panel_id == "folded-bank")
    assert second.chart == "" and second.state == "Stage receipt · chart pending"


def test_coherent_and_signed_studies_link_only_their_exact_manifest_ids(tmp_path):
    root = tmp_path / "acquisition-support"
    signed_lock = root / "phase-scout" / "prediction-lock.json"
    coherent_lock = signed_lock.with_name("coherent-lock.json")
    dump(signed_lock, {"signed": 1})
    dump(coherent_lock, {"coherent": 2})
    stage = root / "stage-charts"
    pages = []
    ids = ("phase-scout", "phase-scout-coherent")
    for ident, receipt in zip(ids, (signed_lock, coherent_lock), strict=True):
        digest = sha256(receipt.read_bytes()).hexdigest()
        pages.append(
            dict(
                id=ident,
                title=ident,
                image=f"{ident}.png",
                sources={receipt.relative_to(tmp_path).as_posix(): digest},
            )
        )
    dump(stage / "manifest.json", dict(version=1, pages=pages[:1]))
    (stage / "phase-scout.png").write_bytes(b"signed chart")
    first = {r.panel_id: r for r in index.stages(root, tmp_path) if r.panel_id in ids}
    assert first[ids[0]].chart == "stage-charts/phase-scout.png"
    assert first[ids[1]].chart == ""
    assert first[ids[1]].state == "Stage receipt · chart pending"
    (stage / "phase-scout-coherent.png").write_bytes(b"coherent chart")
    dump(stage / "manifest.json", dict(version=1, pages=pages))
    final = {r.panel_id: r for r in index.stages(root, tmp_path) if r.panel_id in ids}
    assert {r.chart for r in final.values()} == {f"stage-charts/{ident}.png" for ident in ids}


def test_reference_chart_counts_follow_the_primary_curve_in_each_original_panel(tmp_path):
    atlas = tmp_path / "atlas"
    folder = atlas / "roof" / "c0"
    folder.mkdir(parents=True)
    (folder / "original-ten.csv").write_text(
        "figure,series,decision\n"
        "glrt_batch,baseline,published\n"
        "glrt_batch,one,withheld\n"
        "glrt_batch,four,published\n"
        "glrt_batch,four_forced,diagnostic\n"
        "v5_lean,one,withheld\n"
    )
    refs = list(index.originals(tmp_path, atlas))
    (result,) = [r for r in refs if r.panel_id == "glrt_batch" and r.arm == "c0"]
    (single,) = [r for r in refs if r.panel_id == "v5_lean" and r.arm == "c0"]
    assert len(refs) == 20
    assert result.scheduled == 1 and result.published == 1 and result.withheld == 0
    assert single.scheduled == 1 and single.published == 0 and single.withheld == 1
    assert "four-tile" in result.notes and "single-tile" in single.notes
    assert result.forced_available is None


def test_curvature_comparison_uses_only_its_dedicated_primary_images(tmp_path):
    root = tmp_path / "acquisition-support"
    folder = root / "derivative-receiver"
    overlay = "derivative_receiver-reserve"
    dedicated = f"{overlay}-curvature-only"
    methods = ("derivative_receiver", "polynomial_curvature_only")
    raw = gzip.compress(
        b"\n".join(
            json.dumps(dict(prediction("A", "withheld"), method=m)).encode() for m in methods
        )
    )
    digest = sha256(raw).hexdigest()
    for place, panel, primary in ((folder, overlay, 0), (folder / "curvature-only", dedicated, 1)):
        dump(place / "seal.json", dict(cases=["A"], files={"positions.jsonl.gz": digest}))
        (place / "positions.jsonl.gz").write_bytes(raw)
        dump(
            place / "figures.json",
            dict(
                charts=[
                    dict(
                        id=panel,
                        title=panel,
                        scope="roof",
                        seal="seal.json",
                        caption="Measured roof.",
                        cases="sealed",
                        series=[
                            dict(key="one", value=methods[primary], file="positions.jsonl.gz"),
                            dict(
                                key="stock", value=methods[1 - primary], file="positions.jsonl.gz"
                            ),
                        ],
                    )
                ]
            ),
        )
    gallery = root / "charts"
    manifest = [
        dict(id=panel, arm=arm, image=f"{arm}/{panel}.png")
        for panel in (overlay, dedicated)
        for arm in index.ARMS
    ]
    dump(gallery / "manifest.json", manifest)
    for entry in manifest:
        fig = gallery / entry["image"]
        fig.parent.mkdir(exist_ok=True)
        fig.write_bytes(entry["id"].encode())
    rows = index.build(root, tmp_path / "atlas", tmp_path)
    plotted = {r.chart: r for r in rows if r.chart}
    assert len(plotted) == 4 and all(r.sample == "1 recording" for r in plotted.values())
    assert {(r.panel_id, r.modification) for r in plotted.values()} == {
        (overlay, "polynomial-derivatives"),
        (dedicated, "polynomial-curvature-only"),
    }
    for arm in index.ARMS:
        assert plotted[f"charts/{arm}/{overlay}.png"].panel_id == overlay
        assert plotted[f"charts/{arm}/{dedicated}.png"].panel_id == dedicated
    manifest[-1]["image"] = manifest[1]["image"]
    dump(gallery / "manifest.json", manifest)
    with pytest.raises(ValueError, match="linked from multiple"):
        index.build(root, tmp_path / "atlas", tmp_path)


def test_held_fit_work_uses_capture_era_factors_only_for_the_held_panel():
    root = "constrained-cavity-phase-fit-work"
    assert "narrow factors" in index.scope_for("fit-work", root).boundary
    assert "capture-era factors" in index.scope_for("fit-work", root + "-held-ds29-0357").boundary
