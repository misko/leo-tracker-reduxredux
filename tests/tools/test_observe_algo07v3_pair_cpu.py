from observe_algo07v3_pair_cpu import fields


def test_proc_cpu_columns_with_spaces_and_parentheses_in_comm():
    raw = ('123 (worker (one)) S 1 2 3 0 -1 0 0 0 0 0 '
           '10 11 120 13 20 0 1 0 999 0 0')
    assert fields(raw) == dict(start_ticks=999, child_user_ticks=120, child_system_ticks=13)
