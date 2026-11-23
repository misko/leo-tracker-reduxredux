import json

import pytest

from reports.ALGO08.v3 import prospective_0160_solver as replay
from reports.ALGO08.v3.joint_publication import completed_route
from reports.ALGO08.v3.prospective_0316_solver import saved_inventory


def psi(short, minute):
    return f"some avg10={short} avg60={minute} avg300=0 total=0\nfull avg10=0 avg60=0 avg300=0 total=0\n"


def test_pressure_gate_only_blocks_cold_signed_metadata():
    cold = [dict(resident_pages=1, file_pages=3)]
    warm = [dict(resident_pages=3, file_pages=3)]
    assert replay.cold_gate(cold, (psi(58, 59), psi(58, 59.9))) == "admitted"
    assert replay.cold_gate(cold, (psi(60, 56),)) == "blocked"
    assert replay.cold_gate(cold, (psi(45, 60), psi(45, 50))) == "blocked"
    assert replay.cold_gate(warm, (psi(65, 63),)) == "admitted"


def test_archived_hardlinks_are_observed_without_reading_data(tmp_path):
    snapshot = tmp_path / "snapshot.tle"
    snapshot.write_bytes(b"tle" * 1800)
    link = tmp_path / "archived-binding.tle"
    link.hardlink_to(snapshot)
    data, = replay.observed([link], lambda fd, length: int(length == 5400), 4096)
    assert data["file_pages"] == 2 and data["resident_pages"] == 1
    assert data["inode"] == snapshot.stat().st_ino

    invalid = tmp_path / "redirect.tle"
    invalid.symlink_to(snapshot)
    with pytest.raises(OSError):
        replay.observed([invalid], lambda *_: 1, 4096)


def test_saved_forecasts_and_numerical_switches_stay_pinned():
    forecast = replay.forecast()
    assert forecast["historical_stock_s"] == 12.512649675
    assert forecast["predicted_solve_cpu_s"]["three_sizes_s"] == pytest.approx(8.106107909)
    assert forecast["predicted_solve_cpu_s"]["dense_only_s"] == pytest.approx(4.670439584)
    assert replay.SETTINGS["native_sha"] == replay.NATIVE_SHA
    assert (replay.ISSUED, replay.ADMITTED, replay.ORDER) == (3691, 2354, ("stock", "cumulative"))
    changed = {name for name, pin in replay.FIX_PINS.items() if replay.PINS[name] != pin}
    assert changed == {"joint_publication.py"}


def test_only_the_completed_inference_sets_the_public_route_on_history_retry():
    failed = {"decision": "fallback", "fallback_clocks": {"cpu_s": 0.25}}
    final = {"decision": "complete"}
    regional = [{"result": {"complete": False}}, {"result": {"complete": True}}]
    solve = {"orbit_policy": "history_support"}
    got = completed_route([solve], [failed, final], regional, [(1, 1)], stock=False,
                          early_regional=True, decision="complete")
    assert got == ([final], regional[1:], False, False,
                   {"orbit_policy": "history_support", "attempts": [failed], "early_regional": regional[:1]})
    with pytest.raises(ValueError, match="Unexpected prior inference"):
        completed_route([{"orbit_policy": "stock"}], [failed, final], regional, [(1, 1)], stock=False,
                        early_regional=True, decision="complete")
    with pytest.raises(ValueError, match="one returned research inference"):
        completed_route([solve], [failed, final], regional, [(0, 0), (1, 1)], stock=False,
                        early_regional=True, decision="complete")


def test_history_retry_preserves_an_early_withhold_and_normal_routes():
    failed = {"decision": "fallback"}
    regional = [{"result": {"complete": False}}, {"result": {"complete": True, "would_withhold": True}}]
    solve = {"orbit_policy": "history_support"}
    route = completed_route([solve], [failed], regional, [(1, 1)], stock=False, early_regional=True, decision="withheld")
    assert route[:4] == ([], regional[1:], True, False)
    stock = completed_route([solve], [], [], [], stock=True, early_regional=False, decision="complete")
    assert stock == ([], [], False, False, None)
    empty = completed_route([dict(empty_receiver_withhold=True)], [], [], [], stock=False,
                            early_regional=True, decision="withheld")
    assert empty == ([], [], False, True, None)


def test_sealed_inventory_rejects_changed_manifests_and_waveform_request(tmp_path):
    from leo.contracts.digests import canonical_digest

    original = "/unavailable/original/recording"
    segment = original + "/part"
    contents = dict(recording_name="recording", segments=[dict(path=segment, manifest_digest="sha256:123")])
    digest = canonical_digest(contents)
    request = dict(recording=original, inventory=digest, session="fast-"+digest[7:39],
                   manifests=[[segment+"/manifest.json", "sha256:123"]])
    path = tmp_path / "inventory.json"
    path.write_text(json.dumps(contents))
    binding = saved_inventory(request, path)
    assert binding(None, original, verify_windows=False) == (request["session"], digest, contents)
    with pytest.raises(ValueError, match="cannot authorize waveform"):
        binding(None, original)
    with pytest.raises(ValueError, match="another recording"):
        binding(None, "/unavailable/other", verify_windows=False)
    with pytest.raises(ValueError, match="original path and manifest order"):
        saved_inventory(dict(request, manifests=[]), path)
