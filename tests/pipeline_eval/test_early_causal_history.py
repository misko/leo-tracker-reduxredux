from hashlib import sha256
from importlib import import_module
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import orbit_modes
from leo.sky.propagation import ElementSetCatalogue


@pytest.fixture
def census(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))
    return import_module("early_causal_history").census


def synthetic(monkeypatch):
    previous_text = "same ordered synthetic prior"
    catalogue = ElementSetCatalogue(("usable", "decayed"), (901, 902), (object(), object()))
    digest = sha256(previous_text.encode()).hexdigest()
    metadata = dict(origin_utc_ns=35, cutoff_utc_ns=31)
    source = dict(epoch_utc_ns=10, collected_utc_ns=11, snapshot_digest="signed synthetic source")
    receipt = dict(catalogue_sha256=digest, sources={str(n): source.copy() for n in catalogue.satellite_numbers})

    def parse(text):
        assert text == previous_text
        return catalogue

    def states(selected, origin, times):
        assert origin == metadata["origin_utc_ns"]
        p = np.zeros((len(selected.satellites), len(times), 3))
        v = p + 1.
        good = np.array([n != 902 for n in selected.satellite_numbers], dtype=bool)
        return p, v, good

    def sample(current, locations, offset):
        rows = len(current["position_km"])
        return np.zeros((rows, len(locations), 3)), np.ones((rows, len(locations), 3))

    monkeypatch.setattr(orbit_modes, "parse_element_sets", parse)
    monkeypatch.setattr(orbit_modes, "ecef_states", states)
    monkeypatch.setattr(orbit_modes, "phase_shifted_states", sample)
    numbers = np.array([901, 902, 903])
    bank = dict(norad=numbers, time_s=np.array([0., 1.]), position_km=np.zeros((3, 2, 3)),
                velocity_km_s=np.ones((3, 2, 3)))
    sky = dict(bank=bank, metadata=metadata, nominal_elements={str(n): {} for n in numbers},
               previous_tle=previous_text, previous_receipt=receipt,
               genuine_previous_tle=previous_text, genuine_previous_receipt=receipt)
    scan = SimpleNamespace(previous_tle=previous_text, previous_tle_sha256=digest,
                           norads=numbers, sky=bank, origin_utc_ns=metadata["origin_utc_ns"])
    return sky, scan, source


def test_same_causal_catalogue_has_both_failing_and_successful_selected_paths(census, monkeypatch):
    sky, scan, source = synthetic(monkeypatch)
    health = census(sky, orbit_modes)["prior"]["genuine_previous"]
    assert health["unusable"] == {"902": source}
    assert health["absent"] == 1
    assert orbit_modes.previous_bank(scan, [0])[1] == {0}
    assert orbit_modes.previous_bank(scan, [2])[1:] == (set(), {})
    with pytest.raises(AssertionError):
        orbit_modes.previous_bank(scan, [1])


def test_changed_and_noncausal_prior_receipts_fail_closed(census, monkeypatch):
    sky, _, _ = synthetic(monkeypatch)
    sky["previous_tle"] += "changed text"
    with pytest.raises(ValueError, match="differs from its causal receipt"):
        census(sky, orbit_modes)
    sky["previous_tle"] = sky["genuine_previous_tle"]
    sky["previous_receipt"]["sources"]["902"]["collected_utc_ns"] = 32
    with pytest.raises(ValueError, match="causal view"):
        census(sky, orbit_modes)
