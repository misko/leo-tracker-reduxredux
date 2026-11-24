import json
from pathlib import Path
import sys

import pytest


HERE = Path(__file__).resolve().parents[2] / "reports" / "ALGO08" / "v3"
sys.path.insert(0, str(HERE))

import all_visit_timing as scout
import all_visit_timing_trial as trial


def test_reduction_changes_only_the_timing_loop_and_carrier_count():
    src = """enum { points = 120000, clocks = 12, lags = 8 };
void install(void) { for (int k = 0; k < lags; ++k) { setup(k); } }
static void find_times(TimingFirst *w, int *epochs) {
    for (int k = 0; k < lags; ++k) { correlate(k); }
}
"""
    updated = scout.reduced_source(src)
    assert "points = 120000, clocks = 4, lags = 8" in updated
    assert "setup(k);" in updated and updated.count("k != 5 && k != 6") == 1
    assert updated.index("k != 5 && k != 6") > updated.index("static void find_times")
    with pytest.raises(ValueError, match="changed layout"):
        scout.reduced_source(src.replace("120000", "200000"))


def test_prior_receipt_selects_fastest_scout_with_per_antenna_cover():
    result = trial.prior_science(HERE / "measurements" / "short-timing-lags.json.gz")
    assert result["chosen"] == "two_four"
    assert not result["scores"]["one_four"]["eligible"]
    assert result["scores"]["two_four"]["groups"]["dense-0"] == {"positives": 25, "retained": 21}
    assert trial.minimum(5, 6) and not trial.minimum(11, 14)


def test_pinned_timing_pack_rejects_changed_binary(tmp_path):
    path = tmp_path / "short.so"
    path.write_bytes(b"independently tested timing object")
    info = dict(layout=scout.LAYOUT, baseline_short_sha256=scout.ORIGINAL_SHORT,
                wrapper_sha256=scout.digest(HERE / "all_visit_timing.py"), prior_sha256=scout.PRIOR,
                training={"positive": 12, "empty": 4}, short_sha256=scout.digest(path))
    binding = tmp_path / "short-scout.json"
    binding.write_text(json.dumps(info))
    pin = scout.digest(binding)
    assert scout.read_pack(tmp_path, pin) == (info, path)
    path.write_bytes(b"different")
    with pytest.raises(ValueError, match="Unexpected binding"):
        scout.read_pack(tmp_path, pin)


def test_reduced_scout_flags_require_guarded_port_and_trusted_digest():
    from combined_raw_research import main

    with pytest.raises(SystemExit) as error:
        main(["--eight-ms-native-history", "--short-timing-scout", "/tmp/pack", "--short-timing-scout-sha256", "pin"])
    assert error.value.code == 2


def test_factor_comparison_counts_replacement_and_wrap():
    def factor(epoch, hz):
        return dict(integer_epoch_sample=epoch, fractional_epoch_offset_samples=0., fractional_tracking_cfo_hz=hz,
                    candidate_rank=0, passed_fractional_margin_gate=True)

    left = dict(visit_index=8, receiver_id=0, candidates=[factor(13333, -10_000)])
    wrapped = dict(left, candidates=[factor(1, -10_001)])
    replacement = dict(left, candidates=[factor(1, 10_000)])
    assert trial.compare([left], [wrapped], set())["short-0"]["retained"] == 1
    changed = trial.compare([left], [replacement], set())["short-0"]
    assert changed["retained"] == 0 and changed["missing"] == changed["extra"] == 1
