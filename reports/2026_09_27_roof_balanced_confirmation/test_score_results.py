import json
import score_results as report


def test_missing_search_never_parses_reference(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(report,'HERE',tmp_path)
    monkeypatch.setattr(report.runner,'inputs',lambda:([dict(session_id='a')],{}))
    (tmp_path/'contract.json').write_text('{}')
    (tmp_path/'manifest.json').write_text('this must not be parsed')
    report.main()
    assert 'PENDING' in capsys.readouterr().out
    assert not (tmp_path/'distance_results.json').exists()


def test_incomplete_search_never_parses_reference(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(report,'HERE',tmp_path)
    monkeypatch.setattr(report.runner,'inputs',lambda:([dict(session_id='a')],{}))
    (tmp_path/'contract.json').write_text('{}')
    (tmp_path/'search-a.json').write_text(json.dumps(dict(finished=False)))
    (tmp_path/'manifest.json').write_text('this must not be parsed')
    report.main()
    assert 'PENDING' in capsys.readouterr().out
