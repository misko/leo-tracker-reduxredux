import csv
import json
import re

import pytest

from tools.pipeline_eval.qualification import embedded_figures
from tools.pipeline_eval.qualification import prototype_figures as figures
from tools.pipeline_eval.scoring import ROLES


@pytest.mark.parametrize("arm", ["c0", "fitted_c"])
def test_early_atlas_keeps_measured_attempts_and_scientific_boundaries(arm):
    pages = figures.pages(arm)
    by_id = {p.id: figures._cohorts(p) for p in pages}
    assert len(pages) == len(by_id) == 34
    assert set(embedded_figures.TITLES) <= by_id.keys()

    aborted = by_id["early_events"][figures.ROOF]["candidate"]
    assert len(aborted) == 8
    assert all(row.decision == "withheld" and row.error_km is None for row in aborted)

    geometry = by_id["early_coreset"]
    assert set(geometry[figures.ROOF]) == {*ROLES, "candidate"}
    assert len(geometry[figures.ROOF]["candidate"]) == 8
    assert len(geometry[figures.ROOF]["omitted-tracks"]) == 8
    assert sum(m.error_km is None for m in geometry[figures.ROOF]["omitted-tracks"]) == 1
    assert set(geometry[figures.SIMULATION]) == {"candidate"}
    assert len(geometry[figures.SIMULATION]["candidate"]) == 32
    assert set(geometry[figures.WRONG_TILE]) == {"candidate"}
    assert len(geometry[figures.WRONG_TILE]["candidate"]) == 16
    oracle = by_id["early_known_ids"][figures.SIMULATION]
    assert set(oracle) == {"diagnostic"}
    assert len(oracle["diagnostic"]) == 32

    ranking = by_id["region_rank_full"][figures.OFFERED]
    assert set(ranking) == {*ROLES, "diagnostic"}
    guard = by_id["region_guard_full"][figures.OMITTED]
    assert set(guard) == {"candidate", "diagnostic"}
    assert all(len(group) == 8 for group in guard.values())
    assert sum(row.decision == "published" for row in guard["candidate"]) == (arm == "c0")
    assert all(row.error_km is None for row in guard["candidate"] if row.decision == "withheld")


def test_original_blind_grid_uses_both_offer_conditions_and_only_real_roof_v5():
    by_id = {p.id: figures._cohorts(p) for p in figures.pages("fitted_c")}
    roof = by_id["blind_grid_roof"]
    for panel, denominator, one, four in (
        ("DS26 · common roof panel", 127, 71, 71),
        ("DS29 · blind roof panel", 8, 6, 5),
    ):
        cohort = roof[panel]
        assert set(cohort) == {*ROLES, "one", "one_forced", "four", "four_forced"}
        assert all(len(rows) == denominator for rows in cohort.values())
        assert sum(m.decision == "published" for m in cohort["one"]) == one
        assert sum(m.decision == "published" for m in cohort["four"]) == four

    transfer = by_id["blind_grid_transfer"]
    for dataset, denominator in (
        ("DS29", 8),
        ("StarLoc", 11),
        ("Altrincham", 3),
        ("Synthetic", 40),
    ):
        present = transfer[f"{dataset} · true tile offered"]
        missing = transfer[f"{dataset} · true tile omitted"]
        assert list(present) == list(missing) == ["four", "four_forced"]
        assert len(present["four"]) == len(missing["four"]) == denominator
        assert {m.recording for m in present["four"]} == {m.recording for m in missing["four"]}
        assert not any(m.error_km is not None for m in missing["four"])
    assert not any(
        m.error_km is not None for m in transfer["Altrincham · true tile offered"]["four_forced"]
    )


def test_transfer_plot_labels_a_mixed_unmeasured_position_denominator():
    page = figures.Page(
        "offer",
        "Measured transfer offer",
        "Two scheduled recordings.",
        [
            figures.Mark("Omitted", "one", "candidate", "withheld", None),
            figures.Mark("Omitted", "two", "candidate", "stage_only", None),
        ],
    )
    plot = figures.draw(page, "c0", show_terminal_counts=True)
    try:
        assert any("unmeasured positions" in item.get_text() for item in plot.texts)
        assert "0/2" in plot.axes[0].get_yticklabels()[0].get_text()
    finally:
        figures.plt.close(plot)


def test_standalone_image_manifest_respects_the_requested_calibration_arm(tmp_path, monkeypatch):
    sample = figures.pages("c0")[-2:]
    monkeypatch.setattr(figures, "pages", lambda arm, evidence: sample if arm == "c0" else [])
    result = figures.generate(tmp_path, arms=("c0",))
    assert result == json.loads((tmp_path / "manifest.json").read_bytes())
    assert {entry["arm"] for entry in result} == {"c0"}
    assert len(result) == 2
    for entry in result:
        assert (tmp_path / entry["image"]).read_bytes().startswith(b"\x89PNG")
    assert len(re.findall(rb"/Type /Page\b", (tmp_path / result[0]["pdf"]).read_bytes())) == 2
    with (tmp_path / result[0]["csv"]).open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == sum(len(page.rows) for page in sample)
    readme = (tmp_path / "README.md").read_text()
    assert "c0/modifications.pdf" in readme and "fitted_c/" not in readme
    with pytest.raises(ValueError, match="distinct calibration arms"):
        figures.generate(tmp_path, arms=("c0", "c0"))


def test_offline_atlas_checks_compact_evidence_digest(tmp_path):
    receipt = (figures.REPORT / figures.RECEIPT).read_bytes()
    data = (figures.REPORT / figures.EVIDENCE).read_bytes()
    (tmp_path / figures.RECEIPT).write_bytes(receipt)
    (tmp_path / figures.EVIDENCE).write_bytes(data + b"extra")
    with pytest.raises(ValueError, match="compact prototype predictions differ"):
        figures.pages("c0", tmp_path)
