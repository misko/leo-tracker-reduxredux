from penalty_cross_score import compare


def test_cross_score_compares_under_the_same_penalty():
    rows = compare({5: dict(assigned=100, satellites=3),
                    10: dict(assigned=105, satellites=3),
                    15: dict(assigned=90, satellites=2)})
    assert rows[0]['own_score'] == 85
    assert rows[0]['improvement'] == 5
    assert rows[0]['best_source_penalties'] == [10]
    assert rows[1]['improvement'] == 0
    assert rows[2]['improvement'] == 0
    assert rows[2]['best_source_penalties'] == [10, 15]
