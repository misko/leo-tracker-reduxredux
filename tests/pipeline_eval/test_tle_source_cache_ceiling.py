from pathlib import Path
import sys
from types import SimpleNamespace


HERE = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(HERE))
from tle_source_cache_ceiling import Costs, HOUR, admissible, budget, oldest_by_content


def test_cutoff_applies_to_collection_with_inclusive_window():
    cutoff = 200 * HOUR
    for offset, accepted in [(-1, False), (0, True), (72 * HOUR, True), (72 * HOUR+1, False)]:
        assert admissible(SimpleNamespace(collected_utc_ns=cutoff-offset), cutoff, 72) is accepted


def test_history_uses_oldest_copy_without_destroying_distinct_digest_order():
    class Ref(tuple):
        @property
        def sha256(self):
            return self[1]

    assert oldest_by_content([Ref((9, "A")), Ref((5, "B")), Ref((3, "A"))]) == ((3, "A"), (5, "B"))


def test_count_repetition_separately_from_admissible_persistent_hits():
    old = {"ready", "future_on_first_use", "future_now"}
    costs = {
        "ready": Costs(10, 10, True, .125),
        "future_on_first_use": Costs(12, 12, True, .25),
        "future_now": Costs(10, 9, False, .5),
        "new": Costs(20, 20, True, 1.),
    }
    measured = budget(costs, old, {"ready", "future_now"})
    assert measured["repeated_bodies"] == 3
    assert measured["reusable_bodies"] == 1
    assert measured["reusable_body_records"] == 10
    assert measured["total_rows"] - measured["causal_rows"] == 1
    assert measured["free_repeated_native_parse_cpu_s"] == .125
    assert measured["all_native_parse_cpu_s"] == 1.875
