import json
from collections import Counter
from pathlib import Path
from shutil import copyfile

import pytest

from tools.pipeline_eval.qualification import external_spectrum_position_figures as watson
from tools.pipeline_eval.qualification import screening_figures

REPORT = (
    Path(__file__).resolve().parents[2]
    / "reports/2026_11_19_receiver_screening/receiver-deadline/external-spectrum"
)


@pytest.fixture
def portable_evidence(tmp_path):
    originals = {}
    for receipt in ("prediction-lock.json", "stage-figure-lock.json"):
        names = json.loads((REPORT / receipt).read_bytes())["files"]
        for file in (receipt, *names):
            original = REPORT / file
            originals[file] = original.read_bytes()
            copyfile(original, tmp_path / file)
    return tmp_path, originals


def test_watson_export_keeps_matched_withholds_and_diagnostic_positions(portable_evidence):
    report, originals = portable_evidence
    watson.export(report)
    (chart,) = screening_figures.charts([watson.CHART_ID], report)
    assert chart.scope == "transfer" and chart.version == 2
    assert len(chart.cases) == 8
    zero = chart.page("c0").rows
    fitted = chart.page("fitted_c").rows
    assert Counter(row.decision for row in zero) == {
        "withheld": 24,
        "diagnostic": 18,
        "no_estimate": 6,
    }
    assert Counter(row.decision for row in fitted) == {"unavailable": 24}
    for method in chart.predictions.values():
        for row in method.values():
            assert row["result"]["arms"]["fitted_c"]["reason"] == watson.UNAVAILABLE
    for window in ("230314-06", "230314-18", "230323-06", "230323-18"):
        included = chart.references[f"watson-{window}-present"]["bindings"]
        omitted = chart.references[f"watson-{window}-omitted"]["bindings"]
        for shared in ("observation_sha256", "catalogue_sha256"):
            assert included[shared] == omitted[shared]
        assert included["input_sha256"] != omitted["input_sha256"]
    assert all((report / file).read_bytes() == value for file, value in originals.items())


def test_watson_export_rejects_an_unsealed_score(portable_evidence):
    report, _ = portable_evidence
    amended = report / "scores.json"
    amended.write_bytes(amended.read_bytes() + b"\n")
    with pytest.raises(ValueError, match="sealed stage evidence changed.*scores.json"):
        watson.export(report)
