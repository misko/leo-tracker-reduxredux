import pytest

from tools.pipeline_eval.qualification.channel_dwell_results import connected, fifo
from tools.pipeline_eval.variants import channel_dwell as method


def test_equal_budgets_and_opposite_bank_keep_consecutive_support():
    rows = [(i, 1 + i % 8) for i in range(8 * 600)]
    for mode in method.MODES:
        chosen = method.schedule(rows, 3, mode)
        assert len(chosen) == method.BUDGET[mode]
        small = mode.endswith("96")
        assert {rows[v][1] for v in chosen} == ({3} if small else {3, 7})
        assert chosen[0] == 2 + (8 * 384 if mode.startswith("delayed") else 0)
        assert chosen[1] - chosen[0] == (16 if small else 4)


def test_prefix_retains_selected_packets_both_receivers_and_no_later_clocks():
    entries = [
        {
            "visit_index": i,
            "receiver_id": r,
            "valid_start_counter": 1000 + 50 * i,
            "candidates": [{"original": (i, r)}],
        }
        for i in range(4)
        for r in (0, 1)
    ]
    raw = dict(
        source=dict(probes=entries, sample_rate_hz=1000, probe_ms=20),
        last_sample_counter=1170,
        delivery_clocks=list(range(4)),
        provenance={"excluded_windows": []},
    )
    head = method.prefix(raw, [0, 2], "sha256:receipt")
    assert head["last_sample_counter"] == 1120
    assert head["delivery_clocks"] == [0, 1, 2]
    assert head["source"]["probes"][:2] == entries[:2]
    assert head["source"]["probes"][2:4] == [dict(row, candidates=[]) for row in entries[2:4]]
    assert head["source"]["probes"][4:] == entries[4:6]
    assert raw["source"]["probes"] == entries and len(entries) == 8


def test_connected_counts_use_duration_and_do_not_bridge_a_long_gap():
    short = [0.4 * i for i in range(8)]
    long = [20 + i for i in range(8)]
    data = connected({"a": short + long, "b": [100.0, 200.0]})
    assert data == dict(viable_time_chains=1, biggest_chain=8, longest_time_chain_s=7)


def test_fifo_time_includes_initial_wait_and_queued_original_work():
    terminal, longest = fifo([10.0, 10.71, 11.42], 1.5)
    assert terminal == 14.5
    assert longest == pytest.approx(3.08)
