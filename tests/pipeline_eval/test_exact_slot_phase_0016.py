from copy import deepcopy
import gzip
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from reports.ALGO08.v3 import exact_slot_phase_0016 as study
from reports.ALGO08.v3.anchor_exposure import enroll


def test_build_accepts_disjoint_phase_and_snapshot_ports_only():
    recipe, held, slot = (study.PREFIX + name for name in
                          ("full_short_run.py", "eight_ms_native_receiver.py", "integrated_original_batch.py"))
    ordinary = dict(schema="original", native={"--short-binary": {"sha256": "ordinary"}},
                    sources={recipe: "a", held: "b", slot: "c"})
    guarded = deepcopy(ordinary)
    guarded["sources"].update({recipe: "qualified-a", held: "qualified-b"})
    guarded["native"]["--short-binary"] = dict(path=str(study.DONOR / "shared.so"), sha256=study.SHORT)
    owned = deepcopy(ordinary)
    owned["sources"][slot] = "qualified-c"
    merged, phase, slots = study.build_delta(ordinary, guarded, owned, lambda *arms: {slot})
    assert phase == {recipe, held} and slots == {slot}
    assert merged["sources"] == {recipe: "qualified-a", held: "qualified-b", slot: "qualified-c"}
    assert ordinary["sources"][slot] == guarded["sources"][slot] == "c"
    with pytest.raises(ValueError, match="overlap"):
        study.build_delta(ordinary, guarded, owned, lambda *arms: {recipe})
    guarded["native"]["--new-grid"] = "unqualified"
    with pytest.raises(ValueError, match="charted assets"):
        study.build_delta(ordinary, guarded, owned, lambda *arms: {slot})


def test_only_combined_mounts_the_checkout_overlay_and_asks_for_slots(tmp_path):
    def standard(root, case, work, inputs, role, extra, *, meter):
        assert role == "charted" and meter and case == study.CASE
        return ["--remount-ro", "/", "--", "entry", "--build", str(root / "charted-build.json"),
                "--build-sha256", "pin", *extra]

    panel = SimpleNamespace(command=standard)
    required = study.invoke(panel, tmp_path, {}, "combined", "combined-pin", tmp_path, verify=True)
    regular = study.invoke(panel, tmp_path, {}, "ordinary", "ordinary-pin", tmp_path, verify=True)
    assert required[:3] == ["--ro-bind", str(tmp_path / "worker-sources"), str(study.DONOR / "charted" / study.PREFIX)]
    assert required[required.index("--build") + 1] == str(tmp_path / "charted-build.json")
    assert study.SWITCH in required and study.SWITCH not in regular
    assert "--verify" in required and "--verify" in regular


def test_only_three_sealed_indexes_can_receive_paid_preparation():
    stage = Path("/dev/shm/retained")
    typed = [dict(file=str(stage / f"retained-segment-{segment:08d}" / name), size=size,
                  res=((size+4095)//4096)*4096-3*4096) for (segment, name), (size, _) in study.INDEXES.items()]

    def require_compressed(residency, original, *, page):
        assert original == stage and page == 4096
        if any(not row["file"].endswith(".ci16.zst") for row in residency["nonresident"]):
            raise ValueError("Unapproved non-waveform input")

    panel = SimpleNamespace(bounded_natural_source=require_compressed)
    inputs = dict(staged=stage, files=[row["file"] for row in typed])
    targets, missing = study.preparation_scope(panel, inputs, {"nonresident": typed}, page=4096)
    assert set(targets) == set(inputs["files"]) and missing == 36864
    assert study.preparation_scope(panel, inputs, {"nonresident": []}, page=4096) == ({}, 0)
    with pytest.raises(ValueError, match="Unapproved non-waveform"):
        study.preparation_scope(panel, inputs, {"nonresident": [*typed, dict(file="offered-region.json")]}, page=4096)
    typed[0]["res"] -= 4096
    with pytest.raises(ValueError, match="36,864"):
        study.preparation_scope(panel, inputs, {"nonresident": typed}, page=4096)


def test_measured_seal_replays_ordered_receiver_and_complete_publication_gate():
    receipt = study.HERE / "measurements/exact-slot-phase-0016.json.gz"
    evidence = json.loads(gzip.decompress(receipt.read_bytes()))
    files, packets = evidence["files"], evidence["native_packets"]
    result = files["score.json"]
    ordinary, combined = (result["publications"][role] for role in ("ordinary", "combined"))
    measured = study.compare(ordinary, combined, packets["ordinary"], packets["combined"], enroll, result["identities"])
    assert measured == {key: result[key] for key in ("packet", "science", "identities")}
    assert measured["packet"]["changed_factor_rows"] == {"anchor": 0, "short": 407}
    assert measured["science"]["owners"] == {"c0": 115, "fitted_c": 115}
    assert len(measured["science"]["media"]) == 8
    assert files["ready.json"]["eligibility"]["status"] == "refused"
    assert files["index-preparation.json"]["status"] == "ready"
    assert files["combined-startup-refusal/startup-refusal.json"]["status"] == "no_raw_child"
    assert evidence["measured_pair_order"] == list(study.ORDER)
    last = files["index-preparation.json"]["lease_and_preparation_completed_unix_ns"]
    for role in study.ORDER:
        launch, clock = (files[f"{role}/{name}.json"] for name in ("launch", "process"))
        stamp = launch["event"]["unix_ns"]
        assert last < stamp <= clock["started_unix_ns"] < stamp+2_000_000_000
        assert clock["exit_code"] == 0 and not clock["timed_out"]
        assert clock["finished_unix_ns"] < stamp+30_000_000_000
        last = clock["finished_unix_ns"]
        assert result["clocks"][role]["through_verified_wall_s"] == pytest.approx(
            clock["elapsed_s"]+files[f"{role}/verify-process.json"]["wall_s"])
