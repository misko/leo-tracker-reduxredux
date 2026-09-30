from receive_fifo import run


def test_receive_dequeue_register_bank_and_full_word():
    rows = run()['cases']
    assert len(rows) == 140
    assert {(r['bank'], r['channel']) for r in rows} == {(0, 0), (0, 1), (1, 0), (1, 1)}
    assert all(r['input_word'] == r['translation_argument'] for r in rows)
