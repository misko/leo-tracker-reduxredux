import pytest

from tools.report_native_presence_differential import render, tone_counts


def test_tone_counts_do_not_label_unresolved_rf_as_false_alarms():
    def row(kind, raw, residual, rate=5000000):
        return {
            "rate_hz": rate,
            "provenance": {"kind": kind},
            "raw": {"detected": raw},
            "residual": {"detected": residual},
        }

    rows = [
        row("RF", True, True),
        row("RF+tone", True, True),
        row("tone_control", True, False),
        row("tone_control", False, False),
        row("tone_control", True, True, 2500000),
    ]
    assert tone_counts(rows, 5000000) == (2, 1, 0)
    assert tone_counts(rows, 2500000) == (1, 1, 1)


def test_figure_never_overwrites_or_writes_to_archive(tmp_path):
    output = tmp_path / "existing.png"
    output.write_bytes(b"keep")
    for target in (
        output,
        tmp_path / "/mnt/qnap01/figure.png",
        tmp_path / "/srv/bulk/leo/figure.png",
    ):
        with pytest.raises(ValueError, match="new non-archive"):
            render(tmp_path, target)
    assert output.read_bytes() == b"keep"
