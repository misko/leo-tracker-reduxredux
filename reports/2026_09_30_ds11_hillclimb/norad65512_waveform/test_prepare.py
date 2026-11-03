"""Scientific selection and frequency-convention checks for the IQ pilot."""
import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "ds11_waveform_prepare_test", Path(__file__).with_name("prepare.py")
)
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def track(track_id, shift=0):
    return dict(track_id=track_id, training_mask=[True, False, True],
                visits=[shift+1, shift+2, shift+3], times_s=[1., 2., 3.],
                measured_hz=[100., float("nan"), 120.])


def test_selection_uses_every_training_row_in_frozen_order():
    a, b = prepare.TARGETS
    documents = [track(b, 10), track("unrelated", 20), track(a)]
    rows = prepare.select_training_rows(documents)
    assert [(r["track_id"], r["observation_index"]) for r in rows] == [
        (a, 0), (a, 2), (b, 0), (b, 2)
    ]
    assert [r["visit"] for r in rows] == [1, 3, 11, 13]
    assert [r["measured_hz"] for r in rows] == [100., 120., 100., 120.]
    documents[0]["measured_hz"][1] = -1e30
    documents[2]["measured_hz"][1] = 1e30
    assert prepare.select_training_rows(documents) == rows


def test_missing_target_cannot_reduce_denominator_silently():
    with pytest.raises(ValueError, match="target track absent"):
        prepare.select_training_rows([track(prepare.TARGETS[0])])


@pytest.mark.parametrize("rf_hz", [10.71e9, 11.21e9])
@pytest.mark.parametrize("alias", [-3, 0, 2])
def test_alias_replay_and_residual_mapping_preserve_integer_alias(rf_hz, alias):
    cached = -3123.25
    native = cached + alias / 4.4e-6
    exported = native * 11.2e9 / rf_hz
    replay, actual = prepare.alias_mapping(exported, rf_hz, cached)
    assert actual == alias
    assert replay == pytest.approx(native, abs=1e-8)
    residual = 127.5
    corrected = exported + residual * 11.2e9 / rf_hz
    corrected_native, corrected_alias = prepare.alias_mapping(
        corrected, rf_hz, cached + residual
    )
    assert corrected_alias == alias
    assert corrected_native - replay == pytest.approx(residual, abs=1e-8)


def test_nonintegral_alias_mapping_is_rejected():
    with pytest.raises(ValueError, match="nonintegral"):
        prepare.alias_mapping((2.125 / 4.4e-6) * 11.2e9 / 10.71e9, 10.71e9, 0.)
