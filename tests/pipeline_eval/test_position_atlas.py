import csv
import gzip
import json
from html.parser import HTMLParser

import pytest

from tools.pipeline_eval import __main__ as cli
from tools.pipeline_eval import atlas, figure_books
from tools.pipeline_eval.qualification import atlas_roof
from tools.pipeline_eval.scoring import ROLES


def test_paired_tolerance_is_per_recording_and_counts_withholding(tmp_path):
    path = tmp_path / "comparisons.csv"
    path.write_text(
        "figure,arm,dataset,recording,series,decision,error_km\n"
        "m,c0,DS26,A,baseline,published,1\n"
        "m,c0,DS26,B,baseline,published,4\n"
        "m,c0,DS26,C,baseline,published,2\n"
        "m,c0,DS26,D,baseline,withheld,\n"
        "m,c0,DS26,A,four,published,1.08\n"
        "m,c0,DS26,B,four,published,3.0\n"
        "m,c0,DS26,C,four,withheld,\n"
        "m,c0,DS26,D,four,published,1.0\n"
        "m,c0,DS26,C,four_forced,diagnostic,1.5\n"
    )
    (row,) = atlas.paired_accuracy(path)
    assert [
        row[k]
        for k in (
            "recordings",
            "published",
            "withheld",
            "paired_fixes",
            "error_at_most_105pct_v5",
            "error_at_most_110pct_v5",
        )
    ] == [4, 3, 1, 2, 1, 2]
    assert row["median_published_km"] == 1.08
    with path.open("a") as stream:
        stream.write("m,c0,DS26,E,four,published,0.1\n")
    with pytest.raises(ValueError, match="unmatched"):
        atlas.paired_accuracy(path)
    with path.open("a") as stream:
        stream.write("m,c0,DS26,A,four,published,1.08\n")
    with pytest.raises(ValueError, match="duplicate"):
        atlas.paired_accuracy(path)


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.images = []
        self.choices = []
        self.anchors = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "img":
            self.images.append(values["src"])
        elif tag == "input":
            self.choices.append(values["id"])
        elif tag == "article":
            self.anchors.append(values["id"])


def test_regular_figure_command_outputs_individual_charts_and_paired_counts(tmp_path):
    cli.main(["figures", "--panel", "matched135", "--variant", "v5_lean", "--out", str(tmp_path)])
    doc = Links()
    doc.feed((tmp_path / "index.html").read_text())
    assert doc.choices == ["cal-fitted_c", "cal-c0"]
    assert doc.anchors == ["roof-v5_lean"]
    assert doc.images == ["fitted_c/v5_lean.png", "c0/v5_lean.png"]
    for filename in doc.images:
        assert (tmp_path / filename).read_bytes().startswith(b"\x89PNG")
    with (tmp_path / "paired-v5.csv").open() as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 4
    assert {r["recordings"] for r in rows} == {"127", "8"}
    assert all(r["error_at_most_105pct_v5"] == r["recordings"] for r in rows)


def test_atlas_rejects_partial_selection_and_missing_files(tmp_path):
    with pytest.raises(ValueError, match="includes all measured"):
        cli.main(["figures", "--panel", "atlas", "--variant", "v5_lean", "--out", str(tmp_path)])
    book = atlas.Section("tests", "Tests", [atlas.Chart("x", "Example", {"c0": "x.png"})], {})
    with pytest.raises(FileNotFoundError, match="x.png"):
        atlas.write_index(tmp_path, [book], ["c0"], description="")


def test_offline_chart_search_preserves_the_static_navigation(tmp_path):
    from PIL import Image

    pages = []
    for name, title in (("short_fit", "Short fit"), ("track-search", "Fit & search")):
        Image.new("RGB", (20, 10)).save(tmp_path / f"{name}.png")
        pages.append(atlas.Chart(name, title, {"c0": f"{name}.png"}))
    for count in (1, 2):
        atlas.write_index(
            tmp_path, [atlas.Section("roof", "Roof", pages[:count], {})], ["c0"], description=""
        )
        html = (tmp_path / "index.html").read_text()
        doc = Links()
        doc.feed(html)
        assert doc.anchors == [f"roof-{page.name}" for page in pages[:count]]
        assert all(f'href="#{anchor}"' in html for anchor in doc.anchors)
        assert ('<label for="find-chart">' in html) == (count > 1)
        if count > 1:
            assert '<div class="chart-search" hidden>' in html
            assert 'aria-live="polite"' in html
            assert "Fit &amp; search" in html


def test_recent_pages_link_both_calibrations_and_keep_location_trials_separate():
    def row(name, scope, arm):
        book = "modifications" if scope == "roof" else "transfer"
        return {
            "id": name,
            "title": name,
            "scope": scope,
            "arm": arm,
            "image": f"{arm}/{name}.png",
            "pdf": f"{arm}/{book}.pdf",
            "csv": f"{arm}/{book}.csv",
        }

    arms = ["fitted_c", "c0"]
    manifest = [
        row(n, s, a) for n, s in [("candidate", "roof"), ("wrong", "transfer")] for a in arms
    ]
    roof, other = atlas.short_receiver_sections(manifest, arms)
    assert roof.charts[0].images == {a: f"short-receiver/{a}/candidate.png" for a in arms}
    assert other.charts[0].images == {a: f"short-receiver/{a}/wrong.png" for a in arms}
    assert roof.links["Fitted calibration data"] == "short-receiver/fitted_c/modifications.csv"
    assert other.links["Zero calibration PDF"] == "short-receiver/c0/transfer.pdf"
    with pytest.raises(ValueError, match="different calibration rosters"):
        atlas.short_receiver_sections(manifest[:-1], arms)


@pytest.mark.parametrize("arm", ["c0", "fitted_c"])
def test_followups_supply_physical_positions_on_paired_rosters(arm):
    methods = [*atlas_roof.DETECTORS, *atlas_roof.NEW]
    pages = atlas_roof.roof_pages(arm, methods)
    assert [p.method for p in pages] == methods
    for page in pages:
        series = {m.series for m in page.rows}
        assert {*ROLES, "one"} <= series
        for mode in series:
            assert {m.recording for m in page.rows if m.series == mode} == {
                "DS26-0036",
                "DS29-0082",
            }
        assert not any(m.decision == "stage_only" for m in page.rows)
        if page.method != "pass_geometry":
            assert "stock" in series
            assert all(m.decision == "published" for m in page.rows if m.series in ("stock", "one"))


def test_detector_comparison_rejects_controls_from_different_source(tmp_path):
    directory = "native-geometry"
    for name in ["positions.jsonl.gz", "control-positions.jsonl.gz"]:
        source = atlas_roof.REPORT / directory / name
        rows = list(cli.read_predictions(source).values())
        if name == "positions.jsonl.gz":
            rows[0]["source_archive_sha256"] = "1" * 64
        cli.write(
            tmp_path / directory / name,
            gzip.compress(b"".join(json.dumps(r).encode() + b"\n" for r in rows)),
        )
    with pytest.raises(ValueError, match="unmatched source GLRT"):
        atlas_roof.detector_page("native_geometry", "fitted_c", tmp_path)


def test_reduced_v5_paired_counts_expose_the_recordings_hidden_by_equal_medians():
    archive = figure_books.COLD_START_REPORT / "figures/fitted_c/modifications.csv"
    rows = [
        r
        for r in atlas.paired_accuracy(archive)
        if r["figure"] == "v5_stop_cavity" and r["series"] == "one"
    ]
    assert sum(r["published"] for r in rows) == 135
    assert sum(r["error_at_most_105pct_v5"] for r in rows) == 131
    assert sum(r["error_at_most_110pct_v5"] for r in rows) == 133


def test_complete_atlas_links_every_original_plot_and_preserves_its_scored_samples():
    root = atlas_roof.REPORT
    doc = Links()
    all_charts = (root / "index.html").read_text()
    doc.feed(all_charts)
    assert len(doc.anchors) == len(set(doc.anchors))
    assert len(doc.images) == len(set(doc.images))
    assert all((root / image).is_file() for image in doc.images)
    assert set(figure_books.TEN) == {
        anchor.removeprefix("original-") for anchor in doc.anchors if anchor.startswith("original-")
    }
    for arm in atlas.ARM_LABEL:
        assert all(f"roof/{arm}/{name}.png" in doc.images for name in figure_books.TEN)
        original = figure_books.REPORT / "figures" / arm / "modifications.csv"
        assert (root / "roof" / arm / "original-ten.csv").read_bytes() == original.read_bytes()
    focused = Links()
    focused.feed((root / "original-ten.html").read_text())
    assert 'href="original-ten.html"' in all_charts
    assert focused.anchors == [anchor for anchor in doc.anchors if anchor.startswith("original-")]
    assert set(focused.images) == {
        f"roof/{arm}/{name}.png" for arm in atlas.ARM_LABEL for name in figure_books.TEN
    }


def test_unified_atlas_lists_each_recent_measurement_and_its_calibration_control():
    root = atlas_roof.REPORT
    manifest = json.loads((root / "short-receiver/manifest.json").read_bytes())
    selected = {"roof": set(), "transfer": set()}
    root_links = Links()
    root_links.feed((root / "index.html").read_text())
    recent_links = Links()
    recent_links.feed((root / "short-receiver/index.html").read_text())
    for row in manifest:
        selected[row["scope"]].add(row["id"])
        assert "short-receiver/" + row["image"] in root_links.images
        assert "./" + row["image"] in recent_links.images
        assert f"short-{row['scope']}-{row['id']}" in root_links.anchors
    assert {
        "v5_initial_rank1",
        "v5_first_ranked_broad-replayed",
        "raw_robust-fresh",
        "refine_bank",
        "v5_shared_search",
    } <= selected["roof"]
    assert {
        "anonymous_beacon_arcs",
        "joint_pass_id-wrong-region",
        "joint_pass_id-fresh-scenes",
    } <= selected["transfer"]
    assert len(recent_links.images) == 2 * sum(len(ids) for ids in selected.values())
