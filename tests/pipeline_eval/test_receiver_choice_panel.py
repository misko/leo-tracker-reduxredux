import pytest

from tools.pipeline_eval.qualification import receiver_choice_panel as panel
from tools.pipeline_eval.qualification import receiver_choice_panel_results as results


def row(edge):
    return {"recording": {"segments": [{"path": f"capture-{edge}/segment/manifest.json"}]}}


def test_lower_edge_uses_acquisition_names_without_reordering_hashes():
    def provider(excluded):
        assert excluded == {"already used"}
        ranked = [("c", "DS26-0010", row("lower")), ("a", "DS26-0011", row("upper"))]
        return ranked, {ident: {"state": "metadata eligible"} for _, ident, _ in ranked}

    selected, ledger = panel.lower_edge(provider, {"already used"})
    assert selected == [("c", "DS26-0010", row("lower"))]
    assert ledger["DS26-0010"]["state"] == "metadata eligible"
    assert ledger["DS26-0011"] == {
        "state": "different or undocumented archive edge",
        "archive_edge_name": "upper",
    }


@pytest.mark.parametrize("edge", ("lower", "upper"))
def test_signed_archive_edge_is_required_after_metadata_filter(monkeypatch, edge):
    capture = {"edge": edge, "input_manifest_sha256": "sha256:" + "1" * 64}
    screen = row("lower")

    def authenticate(case):
        assert case == screen
        return capture, 212

    monkeypatch.setattr(panel, "ARCHIVE", authenticate)
    if edge == "lower":
        assert panel.requires_lower(screen) == (capture, 212)
    else:
        with pytest.raises(ValueError, match="signed pilot edge"):
            panel.requires_lower(screen)


def test_bounded_reference_lanes_do_not_change_previous_deployments():
    former = panel.whole.REPORT, panel.reference.REPORT, panel.reference.LANES
    assert panel.WORK != panel.previous.WORK
    with panel.context():
        assert panel.whole.REPORT == panel.REPORT == panel.reference.REPORT
        assert panel.whole.CPUS == {"DS26": [12, 13], "DS29": [14, 15]}
        assert panel.reference.LANES == panel.LANES
        assert set(panel.LANES) == {16, 17}
        assert {role for roles in panel.LANES.values() for role in roles} == set(panel.ROLES)
    assert former == (panel.whole.REPORT, panel.reference.REPORT, panel.reference.LANES)


def test_chart_uses_extended_authority_for_only_new_ds29_and_retains_failed_rows(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(results.screening_figures, "generate", lambda out, evidence: None)
    cases = ["DS26-0001", "DS29-0001"]
    groups = dict(all=cases, ds26=cases[:1], ds29=cases[1:])
    rows = [
        dict(id=ident, method=method, result={"status": "timed_out"})
        for ident in cases
        for method in results.METHODS.values()
    ]
    with panel.context():
        results.figures(tmp_path, groups, rows, ())
    specs = results.whole_iq.read(tmp_path / "figures.json")
    assert specs["version"] == 2
    pooled, ds26, ds29 = specs["charts"]
    assert ds26.get("roof_references") is None
    assert pooled["roof_references"] == ds29["roof_references"] == results.paired.ROOF_REFERENCES
    assert results.rows_from(tmp_path / pooled["series"][0]["file"]) == rows
