from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
import runpy
import sys
from unittest.mock import patch

import numpy as np
import pytest
from sgp4.api import Satrec

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
from causal_body_live import LiveRegional, bind_one
from historical_orbit_index import SourceIndex, VerifiedIndexReader, elected_elements
from leo.analysis.localization_v3.orbits import ecef_states
from leo.operations import localization_v3_inputs as installed
from leo.sky.propagation import ElementSetCatalogue
from solver_exception_0022 import GUARD, GUARD_PIN


pytestmark = pytest.mark.frozen_v5_numerics


FIRST = "1 25544U 98067A   19343.69339541  .00001764  00000-0  38792-4 0  9991"
SECOND = "2 25544  51.6445 211.2001 0007413  17.6667  85.6398 15.50103472202482"


def checksum(row):
    prefix = row[:68]
    return prefix + str(sum(int(c) if c.isdigit() else c == "-" for c in prefix) % 10)


@dataclass(frozen=True, order=True)
class Snapshot:
    collected_utc_ns: int
    text: str
    provider: str = "space-track"

    sha256 = property(lambda s: sha256(s.text.encode()).hexdigest())
    digest = property(lambda s: "sha256:" + s.sha256)
    byte_size = property(lambda s: len(s.text.encode()))


class Archive:
    def __init__(self, items):
        self.items = items
        self.reads = []

    def list_snapshots(self, provider):
        assert provider == "space-track"
        return self.items

    def read(self, snapshot):
        assert snapshot.sha256 == sha256(snapshot.text.encode()).hexdigest()
        self.reads.append(snapshot)
        return snapshot.text


def real_preparation(callback=None):
    orbit = Satrec.twoline2rv(FIRST, SECOND)
    origin = int(datetime(2019, 12, 9, 18, tzinfo=UTC).timestamp()*1e9)
    catalogue = ElementSetCatalogue(("STARLINK SYNTHETIC",), (25544,), (orbit,))
    positions, _, good = ecef_states(catalogue, origin, np.arange(3.))
    assert good.all()
    x, y, z = positions[0, 0]
    latitude, longitude = np.rad2deg([np.arctan2(z, np.hypot(x, y)), np.arctan2(y, x)])
    current = f"0 STARLINK SYNTHETIC\n{checksum(FIRST)}\n{checksum(SECOND)}\n"
    old_line = checksum(FIRST[:18] + "19343.69239541" + FIRST[32:])
    previous = f"0 STARLINK SYNTHETIC\n{old_line}\n{checksum(SECOND)}\n"
    archive = Archive([Snapshot(origin-2_000_000_000, previous), Snapshot(origin, current),
                       Snapshot(origin+5_000_000_000, current), Snapshot(origin+90_000_000_000, current)])
    route = dict(anchor_utc_ns=origin, causal_cutoff_utc_ns=origin+60_000_000_000)
    calls = []

    def prepare():
        parser = VerifiedIndexReader(archive, SourceIndex())
        calls.append(parser)
        with elected_elements(), patch.object(archive, "read", parser.read):
            sky = installed.prepare_initial_sky(archive, [{"times": [0., 10.]}], route,
                element_parser=parser, screen_latitude_deg=latitude, screen_longitude_deg=longitude)
            if callback is not None:
                callback(calls, sky)
            history = installed.prepare_phase_history(archive, sky["nominal_elements"], route, element_parser=parser)
        return dict(status="inputs_prepared", sky=sky, phase_history=history)

    return prepare, calls, archive


def assert_same_preparation(left, right):
    assert left["phase_history"] == right["phase_history"]
    for key in left["sky"]:
        if key == "bank":
            for array in left["sky"][key]:
                np.testing.assert_array_equal(left["sky"][key][array], right["sky"][key][array])
        else:
            assert left["sky"][key] == right["sky"][key]


def test_nested_reviewed_regional_and_actual_sgp4_bank_through_current_phase():
    reviewed = LiveRegional(GUARD, GUARD_PIN)
    support = runpy.run_path(str(GUARD))["corner_support"]
    prepare, calls, archive = real_preparation()
    ordinary = prepare()
    verified_reads = tuple(archive.reads)
    archive.reads.clear()
    audit = {}
    with support(), support():
        owners = reviewed.owners(installed.regional_bank)
        assert len(owners) == 2
        candidate = bind_one(prepare, audit, reviewed)()
        assert all(owner["bank"] is candidate["sky"]["bank"] for owner in owners)
    assert_same_preparation(ordinary, candidate)
    assert tuple(archive.reads) == verified_reads
    assert len(calls) == 2
    actual, = audit["attempts"]
    assert actual["same_phase_handoffs"] == actual["observed_regional_calls"] == 1
    assert actual["counts"]["dominated_latest_rows"] == 1
    assert actual["counts"]["history_success"] == 1


def test_same_label_different_owned_bank_rolls_back_to_ordinary_stage():
    reviewed = LiveRegional(GUARD, GUARD_PIN)
    support = runpy.run_path(str(GUARD))["corner_support"]
    audit = {}

    def swap(calls, sky):
        if len(calls) == 1:
            observed, = reviewed.owners(installed.regional_bank)
            bank = sky["bank"]
            observed["bank"] = dict(bank, position_km=bank["position_km"] + 1.)
            assert np.array_equal(observed["bank"]["norad"], bank["norad"])

    prepare, calls, _ = real_preparation(swap)
    ordinary, _, _ = real_preparation()
    with support():
        candidate = bind_one(prepare, audit, reviewed)()
    assert_same_preparation(ordinary(), candidate)
    assert len(calls) == 2
    row, = audit["attempts"]
    assert row["fallback"] == "phase history did not consume the observed initial sky"
    assert row["same_phase_handoffs"] == 0


def test_unreviewed_same_named_regional_port_is_left_to_the_ordinary_preparation():
    reviewed = LiveRegional(GUARD, GUARD_PIN)
    original = installed.regional_bank

    def regional(*args, **kwargs):
        answer = original(*args, **kwargs)
        bank = answer["bank"]
        return dict(answer, bank=dict(bank, position_km=bank["position_km"] + 1.))

    prepare, calls, _ = real_preparation()
    audit = {}
    with patch.object(installed, "regional_bank", regional):
        assert reviewed.owners(regional) is None
        observed = bind_one(prepare, audit, reviewed)()
        assert_same_preparation(observed, prepare())
    assert len(calls) == 2
    assert audit["attempts"][0]["fallback"] == "unverified active regional or initial port"


def test_missing_observer_source_keeps_the_installed_archive_path(tmp_path):
    reviewed = LiveRegional(tmp_path/"missing.py", GUARD_PIN)
    prepare, calls, _ = real_preparation()
    audit = {}
    with runpy.run_path(str(GUARD))["corner_support"]():
        observed = bind_one(prepare, audit, reviewed)()
    assert observed["status"] == "inputs_prepared"
    assert len(calls) == 1
    assert audit["attempts"][0]["fallback"] == "unverified active regional or initial port"
