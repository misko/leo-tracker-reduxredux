from hashlib import sha256
from importlib import import_module
import json
from pathlib import Path

import pytest


V3 = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"


@pytest.fixture
def trial(monkeypatch):
    monkeypatch.syspath_prepend(str(V3))
    return import_module("north_held_anchor_pair")


def test_prelaunch_census_requires_all_original_pages(trial):
    cache = dict(members=2, observed_members=2, observed_file_pages=3, cached_pages=3, unavailable={})
    trial.require_resident(cache)
    with pytest.raises(ValueError, match="raw cache changed"):
        trial.require_resident(dict(cache, cached_pages=2))
    with pytest.raises(ValueError, match="raw cache changed"):
        trial.require_resident(dict(cache, observed_members=1, unavailable={"EPERM": 1}))


def test_admission_requires_both_archived_routes(trial, monkeypatch, tmp_path):
    controls = {
        "north": dict(previous_chosen_verified=True, factors=456,
                      receipt=dict(choice=dict(route="history"), selected_native_sha256=
                                   "sha256:a03fefaf84057a282a0868ae8a52d34099f530dcf69220360147389e110523c3")),
        "DS30-0016": dict(previous_chosen_verified=True, factors=475,
                          receipt=dict(choice=dict(route="unfiltered"), selected_native_sha256=
                                       "sha256:c09de017909fdc6ffa9b0720b29f3a3fbb84b0785c110f15414ef3fc5bd37589")),
    }
    path = tmp_path / "controls.json"
    monkeypatch.setattr(trial, "CONTROLS", path)

    def record():
        payload = json.dumps(dict(waveform_calls=0, publications=0, controls=controls)).encode()
        path.write_bytes(payload)
        monkeypatch.setattr(trial, "CONTROLS_SHA", sha256(payload).hexdigest())

    record()
    assert trial.admission() == controls
    controls["DS30-0016"]["previous_chosen_verified"] = False
    record()
    with pytest.raises(ValueError, match="Archived chosen-packet parity unavailable for DS30-0016"):
        trial.admission()
