from reports.ALGO08.v3.paid_graph import select


def row(i, frequencies, *, rf=100):
    return dict(visit_index=i, valid_start_counter=i * 10, receiver_id=0, channel=1, actual_rf_hz=rf,
                edge="upper", candidates=[dict(candidate_rank=j, fractional_tracking_cfo_hz=f,
                                               fractional_margin=1 - j / 3, passed_fractional_margin_gate=True)
                                          for j, f in enumerate(frequencies)])


def test_unpaid_or_failed_gate_values_never_enter_graph():
    rows = [row(0, [1, 2]), row(1, [3, 4]), row(2, [5, 6])]
    rows[1]["candidates"] = [None]
    rows[2]["candidates"][1]["passed_fractional_margin_gate"] = False

    def graph(t, f, config):
        assert f == [1, 2, 5] and t == [0., 0., 2.]
        return {"tracks": [{"indices": [1, 2]}]}

    picks, stats = select(rows, {0, 2}, 10, None, graph, True)
    assert [[c["candidate_rank"] for c in p] for p in picks] == [[1], [], [0]]
    assert stats["paid_factors"] == 3 and stats["changed"] == 1


def test_same_epoch_votes_and_rf_isolation():
    rows = [row(0, [1, 2]), row(1, [3]), row(2, [4], rf=101)]

    def graph(t, f, config):
        assert f == [1, 2, 3]
        return {"tracks": [{"indices": [0, 1]}, {"indices": [2]}]}

    picks, stats = select(rows, {0, 1, 2}, 10, None, graph, True)
    assert stats["duplicate_track_epochs"] == 1
    assert [p[0]["candidate_rank"] for p in picks] == [0, 0, 0]
    picks2, stats2 = select(rows, {0, 1, 2}, 10, None, None, False)
    assert picks2 == picks and stats2["tracks"] == 0
