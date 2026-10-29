import pytest
import run_supported_graph_inclusions as runner


def test_only_supported_engine_rows_and_no_error_selection(monkeypatch):
    monkeypatch.setattr(runner, 'identity_consensus', lambda folds, score_name: folds)
    rows = [dict(track_id='a', engine_member=True, error_km=99),
            dict(track_id='b', engine_member=False, error_km=0),
            dict(track_id='c', engine_member=True, error_km=0)]
    results = {key: dict(folds=dict(status=status)) for key, status in
               [('a', 'conditionally_supported_identity'), ('b', 'conditionally_supported_identity'),
                ('c', 'ambiguous_identity')]}
    assert [j['track_id'] for j in runner.supported_jobs(rows, results)] == ['a']
    with pytest.raises(ValueError, match='repeated track'):
        runner.supported_jobs([rows[0], rows[0]], results)
