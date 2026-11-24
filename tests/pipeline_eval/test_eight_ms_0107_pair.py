from importlib import import_module
from pathlib import Path

import pytest


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("eight_ms_0107_pair")


def test_candidate_uses_the_same_native_and_publication_options(trial):
    archived = ["timeout", "--kill-after=2s", "90s", "python", "-IB", "/old/combined_raw_research.py",
                "--eight-ms-native-history", "--catalogue-block-rank", "--prove-no-active-curvature",
                "--recording", "north", "--archive", "old-archive", "--region", "old-offer", "--output", "old-output"]
    result = trial.candidate_command(archived, "physical", "causal", "offer", "out")
    assert result[6:10] == archived[6:10]
    assert result[10:] == ["physical", "--archive", "causal", "--region", "offer", "--output", "out"]
    with pytest.raises(ValueError, match="original full anchors"):
        trial.candidate_command([*archived, "--full-anchor-primary-library"], "physical", "causal", "offer", "out")


def test_both_original_cached_members_are_required(trial):
    resident = dict(members=1, observed_members=1, unavailable={}, observed_file_pages=13, cached_pages=13)
    assert trial.is_resident(dict(payload=resident, index=resident))
    assert not trial.is_resident(dict(payload=resident, index=dict(resident, cached_pages=12)))


def test_positive_withhold_is_distinguished_from_empty_or_fix(trial):
    ready = dict(native_sha256="signed", factors=1, figures={}, sidecars=None,
                 science=dict(receipt={"decision": "withheld"}, reason="no_active_curvature",
                              arms={"c0": {"latlon": None, "rf_rms_hz": None}}),
                 bootstrap=dict(route="authenticated_installed_graph_ineligible", graph_proof={"proven": True, "native_sha256": "signed"}))
    assert trial.ordinary_nonempty_withhold(ready, candidate=True)
    assert not trial.ordinary_nonempty_withhold(dict(ready, factors=0), candidate=True)
    ready["science"]["receipt"]["decision"] = "complete"
    assert not trial.ordinary_nonempty_withhold(ready, candidate=True)
