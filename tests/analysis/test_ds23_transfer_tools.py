"""Membership, unbiased sampling and lossless publication controls."""

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from archive_dataset_manifests import archive, verify_entry  # noqa: E402
from freeze_ds23_dataset import freeze_members, random_sample  # noqa: E402


def member(name, stamp, *, complete=True, kind="fast"):
    return dict(case_id=name, recording_id=name, captured_utc_ns=stamp,
                recording_state="complete" if complete else "incomplete",
                recording_format=kind, dataset_label=name, window_count=2,
                tracking_inputs=[], source_inputs=[],
                raw_recording=dict(identity_sha256=name, root="/read-only/" + name,
                                   chunks=[], segments=[], integrity_errors=[]))


def test_strict_post_parent_boundary_keeps_incomplete_and_all_formats():
    old = [member("parent", 9)]
    newer = [member("boundary", 10), member("new", 11, complete=False),
             member("adaptive", 12, kind="adaptive"), member("future", 21)]
    rows = freeze_members(old, newer, 20, 10, include_parent=False)
    assert [r["recording_id"] for r in rows] == ["new", "adaptive"]
    assert rows[0]["recording_state"] == "incomplete"
    assert all(r["membership_source"] == "post_DS22" for r in rows)
    assert not any(r["tracking_inputs"] for r in rows)


def test_inclusive_choice_is_explicit_and_conflicting_duplicate_time_fails():
    old, newer = [member("parent", 9)], [member("new", 11)]
    assert len(freeze_members(old, newer, 20, 10, include_parent=True)) == 2
    with pytest.raises(ValueError, match="capture time"):
        freeze_members(old, [member("parent", 11)], 20, 10, include_parent=True)


def test_random_sample_is_reproducible_order_independent_and_not_quality_filtered():
    rows = [member(f"S{i:03}", i, complete=False) for i in range(30)]
    a, b = random_sample(rows, 10, 2026101801), random_sample(rows[::-1], 10, 2026101801)
    assert [r["recording_id"] for r in a] == [r["recording_id"] for r in b]
    assert len({r["recording_id"] for r in a}) == 10
    assert all(r["recording_state"] == "incomplete" for r in a)
    with pytest.raises(ValueError, match="fewer"):
        random_sample(rows[:3], 10, 1)


def test_small_authority_publication_preserves_exact_bytes_and_detects_tampering(tmp_path):
    source = tmp_path / "source.json"
    payload = b'{"unordered": 2, "white_space":  1}\n'
    source.write_bytes(payload)
    out = tmp_path / "publication"
    out.mkdir()
    record = archive(str(source), "DS.manifest.json", out)
    assert record["original_sha256"] == hashlib.sha256(payload).hexdigest()
    verify_entry(record, out)
    (out / record["parts"][0]["path"]).write_bytes(payload + b" ")
    with pytest.raises(ValueError, match="changed"):
        verify_entry(record, out)


def test_split_compression_roundtrips_one_contiguous_stream(tmp_path, monkeypatch):
    import archive_dataset_manifests as module

    monkeypatch.setattr(module, "PART_BYTES", 128 * 1024)
    source = tmp_path / "large.json"
    source.write_bytes(np.random.default_rng(19).bytes(1024**2 + 100))
    out = tmp_path / "publication"
    out.mkdir()
    record = archive(str(source), "DS.manifest.json", out)
    assert record["encoding"] == "concatenated-zstd-parts" and len(record["parts"]) > 1
    verify_entry(record, out)


def test_physical_modes_take_the_scan_owned_previous_causal_catalogue(monkeypatch, tmp_path):
    import build_dsx01_orbit_modes as module

    expected = tmp_path / "previous.tle"
    scan = SimpleNamespace(previous_tle_path=expected, case="NEW-SCAN")

    def stop(scan, labels, *, previous_path):
        assert previous_path == expected
        raise LookupError("path verified before propagation")

    monkeypatch.setattr(module, "previous_bank", stop)
    with pytest.raises(LookupError, match="path verified"):
        module.build_modes(scan, [0], [0], "physical")


def test_radio_noise_uses_curvature_only_and_is_independent_of_linear_track_values():
    from ds23_radio_noise import estimate

    t = np.linspace(0, 300, 100)
    rng = np.random.default_rng(88)
    curved = dict(times=t, values=.4 * (t - 150)**2 + rng.normal(0, 80, len(t)),
                  observation_ids=[f"C{i}" for i in range(len(t))],
                  pieces=[dict(start_s=0, end_s=300, degree=2)])
    linear = dict(curved, values=1000000 + t * 300,
                  observation_ids=[f"L{i}" for i in range(len(t))])
    observations = [dict(observation_id=k, fractional_margin=.15)
                    for row in (curved, linear) for k in row["observation_ids"]]
    first = estimate([curved], observations)
    second = estimate([curved, linear], observations)
    assert first["constant_radio_sigma_hz"] == second["constant_radio_sigma_hz"]
    assert 50 < first["constant_radio_sigma_hz"] < 110
    assert second["noise_samples"] == len(t)
    assert set(second["per_observation_noise_sigma_hz"]) == {
        r["observation_id"] for r in observations}


def test_eccentricity_modes_use_the_scan_owned_checksum_bound_causal_catalogue(
    monkeypatch, tmp_path
):
    import dsx01_structured_joint as module

    expected = tmp_path / "previous.tle"
    expected.write_text("scan-owned causal elements\n")
    scan = SimpleNamespace(previous_tle_path=expected, case="NEW-SCAN",
                           receipt={"previous_tle_sha256": hashlib.sha256(
                               expected.read_bytes()).hexdigest()})

    def stop(text):
        assert text == "scan-owned causal elements\n"
        raise LookupError("verified correct scan and checksum before propagation")

    monkeypatch.setattr(module, "parse_element_sets", stop)
    with pytest.raises(LookupError, match="correct scan and checksum"):
        module.eccentricity_bank(scan, [0], [0])
    expected.write_text("changed elements\n")
    with pytest.raises(ValueError, match="causal prior TLE differs"):
        module.eccentricity_bank(scan, [0], [0])
