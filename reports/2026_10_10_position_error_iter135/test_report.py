import json

import pytest
import report


def rows():
    return [
        dict(
            label=f"member-{i}",
            dataset=f"DS{16 + i % 3}",
            arms={
                arm: {
                    name: dict(error_km=value, qualified=True)
                    for name, value in zip(report.NAMES, (3.0, 2.0, 1.0), strict=True)
                }
                for arm in report.ARMS
            },
        )
        for i in range(12)
    ]


def test_full_membership_metrics_and_paired_control_not_archive():
    result = report.summarize(rows())
    fitted = result["full"]["fitted-c"]
    assert fitted["metrics"]["phase"]["mean_km"] == 1
    assert fitted["paired_phase_minus_timestamp"]["improvements"] == 12
    assert fitted["paired_phase_minus_timestamp"]["complete_matched_coverage"]
    assert result["DS17"]["zero-c"]["metrics"]["timestamp"]["expected"] == 4
    json.dumps(result, allow_nan=False)


def test_failure_withholds_full_metrics_and_fallback_explicit():
    data = rows()
    data[0]["arms"]["fitted-c"]["phase"] = None
    result = report.summarize(data)["full"]["fitted-c"]
    assert "mean_km" not in result["metrics"]["phase"]
    assert not result["paired_phase_minus_timestamp"]["complete_matched_coverage"]
    assert result["archive_fallback_sensitivity"]["phase"]["archive_fallbacks"] == 1
    assert result["archive_fallback_sensitivity"]["phase"]["mean_km"] == pytest.approx(14 / 12)


def test_missing_terminal_blocks_reference_port(monkeypatch, tmp_path):
    monkeypatch.setattr(report, "HERE", tmp_path)
    (tmp_path / "protocol.json").write_text(
        json.dumps({"members": [{"label": f"member-{i}"} for i in range(12)]})
    )
    monkeypatch.setattr(
        report.runpy, "run_path", lambda *args: pytest.fail("reference port must stay closed")
    )
    with pytest.raises(ValueError, match="Not terminal"):
        report.main()


def test_foreign_receipt_and_short_membership_rejected(tmp_path):
    with pytest.raises(ValueError, match="all twelve"):
        report.load_receipts({"members": []}, "d", tmp_path)
    plan = {"members": [{"label": f"member-{i}"} for i in range(12)]}
    (tmp_path / "member-0.json").write_text(json.dumps(dict(label="foreign", protocol_sha256="d")))
    with pytest.raises(ValueError, match="Foreign"):
        report.load_receipts(plan, "d", tmp_path)


def test_frequency_effects_are_not_accuracy_and_shapes_checked():
    fit = dict(
        frequency_diagnostics=dict(
            maximum_responsibility=[0.8, 0.7],
            assigned_satellite=[1, 2],
            clutter_probability=[0.1, 0.2],
        )
    )
    effect = report.frequency_effects(fit, fit)
    assert effect["available"] and effect["assignment_changes"] == 0
    assert effect["original"]["nonclutter_mass"] == pytest.approx(1.7)


def test_plot_handles_missing_without_zero_fill(tmp_path):
    data = rows()
    data[0]["arms"]["fitted-c"]["phase"] = None
    path = tmp_path / "plot.png"
    report.plot(data, path)
    assert path.stat().st_size > 1000
