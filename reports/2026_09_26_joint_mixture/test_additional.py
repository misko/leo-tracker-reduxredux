from run_additional import select,EXCLUDED


def test_selection_is_deterministic_stratified_and_ignores_scores():
    rows=[{'session_id':str(rate)+str(i),'sample_rate_hz':rate,'capture_start_utc':'t','track_count':10,'score':i}
          for rate in (2500000,5000000,7500000,10000000) for i in range(3)]
    chosen=select(rows)
    for row in rows:row['score']=-100000
    assert select(list(reversed(rows)))==chosen
    assert len(chosen)==4 and len({s['sample_rate_hz'] for s in chosen})==4
    assert not {s['session_id'] for s in chosen}&EXCLUDED
