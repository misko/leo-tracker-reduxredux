import json
import score_topology_confirmation as scorer


def test_no_partial_amended_cohort_unblinding(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(scorer,'HERE',tmp_path)
    (tmp_path/'manifest.json').write_text('REFERENCE MUST NOT BE PARSED')
    (tmp_path/'inventory.json').write_text(json.dumps([dict(session_id=str(i)) for i in range(4)]))
    scorer.main()
    assert json.loads(capsys.readouterr().out)['complete'] is False
    assert not (tmp_path/'topology_distance_results.json').exists()
