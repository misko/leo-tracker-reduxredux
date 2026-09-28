import json
import score_local_grid as report


def test_missing_grid_keeps_reference_unread(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(report,'HERE',tmp_path)
    monkeypatch.setattr(report.runner,'inputs',lambda:([{'session_id':'a'}],{}))
    (tmp_path/'manifest.json').write_text('invalid JSON must not be read')
    report.main()
    assert 'PENDING' in capsys.readouterr().out
    assert not (tmp_path/'local-grid-distances.json').exists()


def test_incomplete_grid_is_not_a_completed_cohort(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(report,'HERE',tmp_path)
    monkeypatch.setattr(report.runner,'inputs',lambda:([{'session_id':'a'}],{}))
    (tmp_path/'local-grid-a.json').write_text(json.dumps({'finished':False}))
    (tmp_path/'manifest.json').write_text('invalid JSON must not be read')
    report.main()
    assert 'PENDING' in capsys.readouterr().out
    assert not (tmp_path/'local-grid-distances.json').exists()
