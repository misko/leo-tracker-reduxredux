import json

import pytest
from PIL import Image

from tools.pipeline_eval import atlas
from tools.pipeline_eval.qualification.gallery_check import (
    _assets,
    _position_counts,
    _transfer_counts,
    check,
)
from tools.pipeline_eval.qualification.pass_geometry_trials import OUTPUT, write_synthetic_figure
from tools.pipeline_eval.scoring import ROLES


def test_gallery_opens_individual_images_and_rejects_wrong_calibration(tmp_path):
    arms = ("fitted_c", "c0")
    files = {}
    for arm in arms:
        directory = tmp_path / arm
        directory.mkdir()
        path = directory / "Doppler chart #1.png"
        Image.new("RGB", (20, 10), "white").save(path)
        files[arm] = str(path.relative_to(tmp_path))
    sections = [atlas.Section("roof", "Roof", [atlas.Chart("test", "Doppler", files)], {})]
    atlas.write_index(tmp_path, sections, arms, description="Matched waveform replay")
    count, actual_arms, images, _ = _assets(tmp_path)
    assert count == 1 and set(arms) == actual_arms
    assert images == {tmp_path / path: "Doppler" for path in files.values()}

    index = tmp_path / "index.html"
    index.write_text(index.read_text().replace('class="arm-fitted_c"', 'class="arm-c0"'))
    with pytest.raises(ValueError, match="mislabeled|other calibration"):
        _assets(tmp_path)


def test_gallery_checks_download_links(tmp_path):
    path = tmp_path / "book.pdf"
    path.touch()
    png = tmp_path / "c0" / "test.png"
    png.parent.mkdir()
    Image.new("RGB", (20, 10)).save(png)
    sections = [
        atlas.Section(
            "roof",
            "Roof",
            [atlas.Chart("test", "Doppler", {"c0": "c0/test.png"})],
            {"PDF": "book.pdf"},
        )
    ]
    atlas.write_index(tmp_path, sections, ("c0",), description="")
    assert _assets(tmp_path)[3] == {png, path}
    path.unlink()
    with pytest.raises(ValueError, match="book.pdf"):
        _assets(tmp_path)


def test_pass_geometry_pdf_uses_the_linked_two_case_scores(tmp_path):
    folder = tmp_path / "cold-transfer"
    folder.mkdir()
    png = folder / "pass-geometry-synthetic.png"
    pdf = png.with_suffix(".pdf")
    score = folder / "pass-geometry-synthetic-scores.json"
    source = (OUTPUT / "synthetic-scores.json").read_bytes()
    score.write_bytes(source)
    write_synthetic_figure(score, png, pdf_path=pdf)
    downloads = {
        "PDF": pdf.relative_to(tmp_path).as_posix(),
        "Scores": score.relative_to(tmp_path).as_posix(),
    }
    chart = atlas.Chart(
        "pass_geometry", "Doppler pass geometry", {"both": png.relative_to(tmp_path).as_posix()}
    )
    atlas.write_index(
        tmp_path,
        [atlas.Section("cold", "Cold", [chart], downloads)],
        ("c0", "fitted_c"),
        description="",
    )
    result = check(tmp_path)
    assert result["pdf_pages"] == {downloads["PDF"]: 1}
    assert result["charts_without_pdf_data"] == []

    score.write_bytes(source + b"\n")
    with pytest.raises(ValueError, match="does not bind the linked synthetic score bytes"):
        check(tmp_path)

    altered = json.loads(source)
    shuffled = next(row for row in altered["scores"] if row["id"] == "generated-null")
    shuffled["arms"]["c0"]["forced_km"] = 0.7
    score.write_text(json.dumps(altered))
    with pytest.raises(ValueError, match="shuffled case has no geographic reference"):
        check(tmp_path)

    wrong_roster = json.loads(source)
    wrong_roster["scores"].append(wrong_roster["scores"][0])
    score.write_text(json.dumps(wrong_roster))
    with pytest.raises(ValueError, match="one signal and one shuffled case"):
        check(tmp_path)


def test_roof_counts_keep_withholding_and_unmeasured_rows_distinct():
    rows = [
        dict(dataset="DS26", series=role, recording=case, error_km="1.4", decision="published")
        for role in ROLES
        for case in ("A", "B")
    ]
    rows.extend(
        dict(dataset="DS26", series="one", recording=case, error_km="", decision="withheld")
        for case in ("A", "B")
    )
    text = "DS26 2/2 2/2 2/2 2/2 0/2 No published fixes (0/2)"
    _position_counts(rows, text, roof=True)
    with pytest.raises(ValueError, match="omits position counts"):
        _position_counts(rows, text.replace("2/2", "2/1", 1), roof=True)
    with pytest.raises(ValueError, match="needs a zero-fix label"):
        _position_counts(rows, text.replace("No published fixes", "Unmeasured"), roof=True)
    rows[-1]["error_km"] = "0.5"
    with pytest.raises(ValueError, match="withheld has an inconsistent error"):
        _position_counts(rows, text, roof=True)
    for row in rows[-2:]:
        row.update(error_km="", decision="stage_only")
    with pytest.raises(ValueError, match="unmeasured label"):
        _position_counts(rows, text, roof=True)
    _position_counts(rows, text.replace("0/2", "Position unmeasured"), roof=True)


def test_gallery_distinguishes_null_truth_publications_from_scored_errors():
    rows = [
        dict(
            dataset="Shuffled detections",
            series="candidate",
            recording="A",
            decision="published",
            error_km="",
        ),
        dict(
            dataset="Shuffled detections",
            series="stock",
            recording="A",
            decision="withheld",
            error_km="",
        ),
    ]
    text = "Shuffled detections Candidate 1/1 · 0 scored Stock 0/1"
    _position_counts(rows, text)
    with pytest.raises(ValueError, match="geographic score"):
        _position_counts(rows, text.replace("1/1 · 0 scored", "0/1"))


def test_gallery_checks_terminal_failure_counts_and_accepts_legacy_archives():
    rows = [
        dict(dataset="DS26", series=series, recording=case, error_km="", decision="timed_out")
        for series in (*ROLES, "one", "stock")
        for case in ("A", "B")
    ]
    _position_counts(rows, f"DS26 {'0/2 ' * len(ROLES)} unmeasured", roof=True)
    text = f"DS26 {'0/2 ' * len(ROLES)} 0/2 · timed out 0/2 · timed out"
    _position_counts(rows, text, roof=True)
    with pytest.raises(ValueError, match="terminal failure counts"):
        _position_counts(rows, text.replace("0/2 · timed out", "0/1 · timed out", 1), roof=True)


def test_permuted_late_observations_can_retain_a_measured_geographic_reference():
    row = dict(
        dataset="Late blocks shuffled",
        series="diagnostic",
        recording="field capture",
        decision="diagnostic",
        error_km="6.91",
    )
    _position_counts([row], "Late blocks shuffled 1/1")
    for label in ("Lane shuffle", "Shuffled detections · no site", "Control · no geographic truth"):
        with pytest.raises(ValueError, match="null geographic control"):
            _position_counts([dict(row, dataset=label)], f"{label} 1/1")


def test_transfer_counts_bind_the_missing_region_label_to_false_publications():
    row = dict(
        correct_region_offered="False",
        series="candidate_published",
        dataset="Synthetic",
        acquisition_id="shared-capture",
        query_id="test",
        error_km="12.4",
        decision="published",
        false_publication="True",
    )
    present = dict(
        row, correct_region_offered="True", query_id="control", false_publication="False"
    )
    text = "Correct region offered Correct region omitted False publications 1/1 1/1"
    _transfer_counts([row, present], text)
    with pytest.raises(ValueError, match="geographic label"):
        _transfer_counts([row, present], text.replace("Correct region omitted", "Second view"))
    with pytest.raises(ValueError, match="wrong-region publication flag"):
        _transfer_counts([dict(row, false_publication="False"), present], text)
    with pytest.raises(ValueError, match="different acquisitions"):
        _transfer_counts([row, dict(present, acquisition_id="unmatched-capture")], text)
