import pytest

from reports.ALGO08.v3.field_fallback_first70 import Reads, compact_route, wall_results


def boot(choice="lean", recipe="screened-tiled-finish"):
    return {"route": "history_risk_installed", "solver_recipe": {
        "specification_solver": recipe, "history_risk": {"choice": choice},
    }}


def test_compact_marker_distinguishes_executed_from_requested_route():
    empty = {"screened_nomination": {}}
    screened = {"screened_nomination": {"screen_nodes": 3}}
    assert compact_route(boot(), empty, "complete") == "lean_complete"
    assert compact_route(boot(), screened, "complete") == "lean_then_fallback"
    assert compact_route(boot("named"), screened, "complete") == "direct_named"
    withheld = {"route": "authenticated_installed_graph_ineligible"}
    assert compact_route(withheld, {}, "withheld") == "before_solver"
    with pytest.raises(ValueError, match="cannot prove"):
        compact_route(boot(), empty, "withheld")
    with pytest.raises(ValueError, match="contract changed"):
        compact_route(boot(recipe="other"), screened, "complete")


def test_logical_byte_cap_prevents_opening_witness_body(tmp_path):
    path = tmp_path / "stage.json"
    path.write_bytes(b'{"a":1}')
    reads = Reads()
    with pytest.raises(ValueError, match="byte bound"):
        reads.load(path, "full_witness", cap=5)
    assert sum(reads.bytes.values()) == 0
    assert reads.load(path, "compact_marker", cap=7) == {"a": 1}
    assert reads.bytes == {"compact_marker": 7}


def test_wall_totals_subtract_each_disjoint_stage_and_keep_all_paid_pairs():
    def elapsed(seconds):
        return {"elapsed_s": seconds}

    records = [
        (elapsed(20), elapsed(15), {"rejected": elapsed(2), "fallback": elapsed(4)}),
        (elapsed(10), elapsed(5), {"rejected": elapsed(0), "fallback": elapsed(0)}),
    ]
    result = wall_results(records)
    assert result["observed"] == dict(installed_s=30, installed_median_s=15, successor_s=20,
                                      successor_median_s=10, at_half=1)
    assert result["skip_failed_proposal"]["successor_s"] == 18
    assert result["free_named_fallback"]["successor_s"] == 16
    assert result["both_free"]["successor_s"] == 14
    assert result["both_free"]["at_half"] == 2
