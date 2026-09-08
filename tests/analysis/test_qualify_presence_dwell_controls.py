import numpy as np
import pytest

from tools.qualify_presence_dwell_controls import generate, summarize


@pytest.mark.parametrize("rate", [2500000, 5000000])
@pytest.mark.parametrize("window", [0, 3, 5])
def test_known_pilot_is_local_to_declared_window(rate, window):
    signal, truth = generate(rate, "upper", 1901, "pilot", window)
    noise, negative = generate(rate, "upper", 1901, "white_noise")
    assert signal.dtype == np.int16 and signal.shape == (6 * rate // 50, 2)
    assert truth["starlink_model_present"] and not negative["starlink_model_present"]
    difference = np.any(signal != noise, axis=1).reshape(6, rate // 50).any(axis=1)
    assert difference.tolist() == [index == window for index in range(6)]
    again, repeated = generate(rate, "upper", 1901, "pilot", window)
    np.testing.assert_array_equal(again, signal)
    assert truth == repeated
    assert truth["fractional_delay_samples"] == 0.35


@pytest.mark.parametrize(
    "kind", ["white_noise", "colored_noise", "tone", "two_tones", "pulsed_tone"]
)
def test_controls_never_claim_a_starlink_model(kind):
    values, truth = generate(2500000, "lower", 1901, kind)
    assert values.shape == (300000, 2)
    assert not truth["starlink_model_present"] and truth["window"] is None
    assert truth["clipped_components"] == 0


def test_bad_geometry_or_unbounded_signal_interval_is_rejected():
    for rate, edge, kind, window in (
        (3000000, "lower", "tone", None),
        (2500000, "bad", "tone", None),
        (2500000, "lower", "bad", None),
        (2500000, "lower", "pilot", True),
        (2500000, "lower", "pilot", 6),
        (2500000, "lower", "tone", 1),
    ):
        with pytest.raises(ValueError):
            generate(rate, edge, 1901, kind, window)


def test_summary_keeps_false_flags_and_missed_signal_windows():
    rows = [
        {
            "truth": {
                "rate_hz": 5000000,
                "kind": "pilot",
                "window": 4,
                "starlink_model_present": True,
            },
            "result": {"rank": {"order": [0, 4, 1, 2, 3, 5]}},
            "flags": [False, True, False, False, False, False],
        },
        {
            "truth": {
                "rate_hz": 5000000,
                "kind": "tone",
                "window": None,
                "starlink_model_present": False,
            },
            "result": {"rank": {"order": list(range(6))}},
            "flags": [True, False, False, False, False, False],
        },
    ]
    result = summarize(rows)["5000000"]
    assert result["pilot"]["policies"]["1"] == {"flagged": 0, "signal_window_selected": 0}
    assert result["pilot"]["policies"]["2"] == {"flagged": 1, "signal_window_selected": 1}
    assert result["tone"]["policies"]["1"]["flagged"] == 1
