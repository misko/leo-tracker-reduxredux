from prepare_four_scan_comparison import selection


def test_selection_is_time_based_not_fit_based_and_excludes_endpoints():
    rows=[dict(session_id=str(i),capture_start_utc_ns=i) for i in range(17)]
    result=selection(dict(dataset_id='DS13',captures=rows[::-1]))
    assert [r['session_id'] for r in result]==['3','6','10','13']
