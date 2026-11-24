"""Check the complete original chronology and the paid correction witness."""

from collections import Counter
from contextlib import contextmanager
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]/"reports/ALGO08/v3"))
from continued_cfo import ContinuedChanges, lane_key, raw_entry
from held_cycle_refined import CFO, FACTOR_FIELDS


def probe(i, radio=0, frequency=None):
    candidates = []
    if frequency is not None:
        candidates = [dict(zip(FACTOR_FIELDS, (0, 100, .25, frequency, .4, .1), strict=True),
                           fractional_margin=.3, passed_fractional_margin_gate=True)]
    return dict(visit_index=i, receiver_id=radio, valid_start_counter=i*10_000_000,
                channel=1, actual_rf_hz=10_000_000, edge="lower", candidates=candidates)


def test_rejected_original_positives_and_an_unpaid_anchor_advance_physical_history():
    select = ContinuedChanges()
    rows = [probe(i, frequency=1000.+100*i) for i in range(4)]
    assert [select.consider(row, short=(i>0)) for i,row in enumerate(rows)] == [False, False, False, True]
    assert select.paid == [lane_key(rows[3])]
    assert [bool(row["candidates"]) for row in select.projected_history(rows)] == [False, False, False, True]
    for i in range(4, 16):
        assert not select.consider(probe(i), short=True)
    assert not select.consider(probe(16, frequency=2600.), short=True)


def test_only_paid_corrections_restore_original_pre_cfo_history():
    select = ContinuedChanges()
    rows = [probe(i, radio=r, frequency=1000.+100*i if r == 0 else None)
            for i in range(4) for r in (0,1)]
    assert [select.consider(row, short=row["visit_index"]>0) for row in rows].count(True) == 1
    source = tuple(rows[6]["candidates"][0][k] for k in FACTOR_FIELDS)
    def amend(factors):
        (item,) = factors
        return ((item[:3]+(2400.,)+item[4:]),), "updated"

    policy = SimpleNamespace(amend=amend)
    with select.capture(policy):
        assert policy.continued_changes is select
        (revised,), _ = policy.amend((source,))
    assert not hasattr(policy, "continued_changes")
    native = [*rows]
    native[6] = dict(rows[6], candidates=[dict(rows[6]["candidates"][0], **{CFO: revised[3]})])
    packet = dict(source=dict(probes=native), provenance=dict(processed_windows=4, invalid_capture=0, window_count=4))
    select.bind_attempts(packet)
    assert select.original_rows(native) == rows
    assert select.projected_history(native)[6]["candidates"][0][CFO] == 2400.
    with pytest.raises(ValueError, match="different signed chronology"):
        select.projected_history(native[::-1])


def test_verified_guard_delegates_to_the_real_continuation_gate(monkeypatch):
    import anchored_cfo_raw as guard
    import held_cycle_refined as selection

    exact, mixed = guard.exact, guard.mixed
    base = exact.RefinedShortDetector
    original_detector, original_recipe = base.detector, guard.recipe
    tail = []
    full = SimpleNamespace(close=lambda: tail.append("closed"))
    pack = Path("reviewed")
    paths = {"original-cfo.so": pack / "original-cfo.so"}

    @contextmanager
    def source(self, *args, **kwargs):
        # The guarded native opener is scoped to entering the receive context.
        assert mixed.NativePath is not workspace

        def receive(window):
            if window.index:
                self.visits["short_primary"] += 1
            return [probe(window.index, frequency=1000.+100*window.index), probe(window.index, radio=1)]

        yield receive

    def workspace(*args):
        return full

    def refine(row, waveform, native, policy, center):
        assert native is full and center == 20
        tail.append(lane_key(row))
        return row, "updated", True

    def launch(library, args):
        assert library == paths["original-cfo.so"]
        assert args == ["--named-survivor-finish", "--select-before-cfo"]
        assert selection.FrequencyChanges is ContinuedChanges
        policy = exact.recipe({}, "stock-recipe")
        assert {"guarded_phase", "continued_cfo", "fixed_epoch_cfo_refinement"} <= policy.keys()
        detector = object.__new__(guard.GuardedDetector)
        detector.policy = SimpleNamespace(continued_changes=ContinuedChanges())
        detector.visits, detector.lanes = Counter(), {}
        detector.cpu_ns = detector.wall_ns = 0
        with detector.detector("method", "lower", binary="verified", pilot="pilot") as receive:
            for index in range(4):
                window = SimpleNamespace(index=index, target={"rf_center_hz": 121, "lnb_lo_hz": 1},
                                         acquisition={"actual_if_center_hz": 100}, samples=None)
                assert len(receive(window)) == 2
        assert detector.lanes[("lower", 0)] == {"attempted": 1, "updated": 1, "changed": 1}
        assert len(detector.policy.continued_changes.lanes) == 8

    monkeypatch.setattr(guard, "verified_pack", lambda origin: paths if origin == pack else None)
    monkeypatch.setattr(guard, "guarded_probe", refine)
    monkeypatch.setattr(mixed, "NativePath", workspace)
    monkeypatch.setattr(mixed, "verified", lambda *args: b"\0\0\0\0")
    monkeypatch.setattr(mixed.MixedApertureDetector, "detector", source)
    monkeypatch.setattr(exact, "run_cli", launch)
    raw_entry(None, ["--named-survivor-finish"], guarded_pack=pack)
    assert tail == [(3, 0), "closed"]
    assert exact.RefinedShortDetector is base and base.detector is original_detector
    assert guard.recipe is original_recipe and selection.FrequencyChanges is not ContinuedChanges


def test_north_verification_detects_signed_factor_and_opportunity_differences():
    from continued_cfo_north_trial import compare_rows

    original = [probe(0, frequency=-1800), probe(1)]
    revised = [probe(0, frequency=-1795), probe(1)]
    assert compare_rows(original, original)["changed_lanes"] == 0
    result = compare_rows(revised, original)
    assert result["changed_lanes"] == 1 and result["max_changed_cfo_hz"] == 5
    with pytest.raises(ValueError, match="chronological opportunity"):
        compare_rows(original[::-1], original)


def test_mirror_enrollment_rejects_substituting_the_containing_offer(monkeypatch, tmp_path):
    import continued_cfo_north_mirror as mirror

    packet = tmp_path / "detections.json"
    raw = {"native_sha256": "sha256:packet", "detector_recipe_sha256": "sha256:policy"}
    offer = {"center": [0, 1], "width_km": 25}
    request = dict(session="session", inventory="inventory", mirror_offer=offer)
    source = {
        tmp_path / "sealed.json": dict(packet=str(packet), raw=raw, binding_sha256="binding",
                                       comparisons={"factors": True}),
        tmp_path / "binding.json": dict(request=request, libraries={}),
        packet: {},
        mirror.MIRROR: offer,
    }
    monkeypatch.setattr(mirror, "CONTAINING", tmp_path)
    monkeypatch.setattr(mirror, "native_file", lambda _: packet)
    monkeypatch.setattr(mirror, "bind_native", lambda *args, **kwargs: None)
    monkeypatch.setattr(mirror, "checked", lambda path, pin: json.dumps(source[path]).encode())
    assert mirror.enrollment()[1] == packet
    source[mirror.MIRROR] = dict(offer, center=[0, 0])
    with pytest.raises(ValueError, match="originally assigned near-omitted"):
        mirror.enrollment()
