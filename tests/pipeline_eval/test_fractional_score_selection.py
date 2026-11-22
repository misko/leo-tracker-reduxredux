import ctypes as ct
from hashlib import sha256
from types import SimpleNamespace

import numpy as np
import pytest

from tools.pipeline_eval.qualification import experimental_publication as publication
from tools.pipeline_eval.variants.experimental import fractional_score_selection as bridge


def window(index):
    acquisition = dict(global_visit=index, sample_start=index * 2_000_000, actual_if_center_hz=0)
    target = dict(channel=1, edge="upper", rf_center_hz=0, lnb_lo_hz=0)
    return SimpleNamespace(acquisition=acquisition, target=target, sample_rate_hz=10_000_000,
                           receiver_ids=(0,), samples=np.zeros((200_000, 2, 2), dtype="<i2"))


def test_two_factors_are_repaired_before_one_continuation_call(monkeypatch, tmp_path):
    binary = tmp_path / "receiver.so"
    binary.touch()
    pilot = tmp_path / "upper.f32"
    np.zeros(133_413, dtype="<f4").tofile(pilot)
    first = (0, 150, .25, 1000., .10, .05)
    second = (1, 854, -.25, -300_000., .10 + 1e-14, .05)
    trace = []

    def native(_binary, _asset):
        input_rows = iter(((second, first), (second, first), (first,), (second, first)))

        def measure(_ctx, _iq, _lane, _lo, _hi, out):
            rows = next(input_rows)
            for index, row in enumerate(rows):
                out[index] = bridge.Factor(*row)
            return len(rows)

        def repair(_ctx, pointer):
            factor = ct.cast(pointer, ct.POINTER(bridge.Factor)).contents
            trace.append(("repair", factor.rank))
            factor.exact = .10
            return 1

        return SimpleNamespace(ctx=1, close=lambda: trace.append(("close",)),
                               lib=SimpleNamespace(cancellation_factors=measure,
                                                   experimental_repair_fractional_selection=repair))

    class Continuation(bridge.Continuation):
        def select(self, row):
            outcome = super().select(row)
            trace.append(("select", outcome))
            return outcome

    monkeypatch.setattr(bridge, "Native", native)
    monkeypatch.setattr(bridge, "Continuation", Continuation)
    for _ in range(2):
        trace.clear()
        counts = dict(two_factor_lanes=0, two_factor_repairs=0,
                      retained_single_repairs=0, already_exact=0)
        with bridge.detector("cancellation", "upper", binary=binary, pilot=pilot,
                             verified_library=binary, counts=counts) as receiver:
            rows = [receiver(window(index))[0] for index in range(4)]
            assert all(not row["candidates"] for row in rows[:3])
            retained, = rows[3]["candidates"]
            assert retained == bridge._candidate(bridge.Factor(*first))
            assert trace[-3:] == [("repair", 1), ("repair", 0), ("select", (0, 0, [3, 2]))]
            assert sum(event[0] == "select" for event in trace) == 4
            assert counts == dict(two_factor_lanes=3, two_factor_repairs=6,
                                  retained_single_repairs=0, already_exact=0)
        assert trace[-1] == ("close",)
        with pytest.raises(RuntimeError, match="closed"):
            receiver(window(4))


def test_incorrect_library_path_or_abi_is_rejected(monkeypatch, tmp_path):
    wanted = tmp_path / "selected.so"
    wanted.touch()
    wrong = tmp_path / "parent.so"
    wrong.touch()
    pilot = tmp_path / "upper.f32"
    np.zeros(133_413, dtype="<f4").tofile(pilot)
    closed = []
    monkeypatch.setattr(bridge, "Native", lambda *_: SimpleNamespace(
        lib=SimpleNamespace(cancellation_factors=lambda *_: 0), close=lambda: closed.append(True),
    ))
    with (
        pytest.raises(ValueError, match="checked cancellation library"),
        bridge.detector("cancellation", "upper", binary=wrong, pilot=pilot, verified_library=wanted),
    ):
        pass
    assert not closed
    with (
        pytest.raises(ValueError, match="reviewed receiver ABI"),
        bridge.detector("cancellation", "upper", binary=wanted, pilot=pilot, verified_library=wanted),
    ):
        pass
    assert closed == [True]


def test_publication_binds_both_selected_source_and_consumer_library(monkeypatch, tmp_path):
    entry = tmp_path / "tools/pipeline_eval/qualification/experimental_publication.py"
    source = tmp_path / publication.FRACTIONAL_SELECTION_SOURCE
    source.parent.mkdir(parents=True)
    source.write_bytes(b"reviewed bridge")
    library = tmp_path / "receiver.so"
    library.write_bytes(b"reviewed native library")
    pin = sha256(library.read_bytes()).hexdigest()
    specification = dict(detector_sha256=pin, sources={
        str(publication.FRACTIONAL_SELECTION_SOURCE): sha256(source.read_bytes()).hexdigest(),
        library.name: pin,
    })
    target = object()
    monkeypatch.setattr(publication, "__file__", str(entry))
    monkeypatch.setattr(publication.util, "find_spec", lambda _: SimpleNamespace(origin=source))
    monkeypatch.setattr(publication, "import_module", lambda _: SimpleNamespace(
        detector=target, LIBRARY_SHA256=pin,
    ))
    assert publication._checked_fractional_score_selection(specification, library) == (
        target, b"reviewed native library",
    )
    library.write_bytes(b"different native library")
    with pytest.raises(ValueError, match="differs from the reviewed build"):
        publication._checked_fractional_score_selection(specification, library)
    source.write_bytes(b"different bridge")
    with pytest.raises(ValueError, match="pinned bundle source"):
        publication._checked_fractional_score_selection(specification, library)
