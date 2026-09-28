import pytest
from score_confirmation import summarize, verify_result


def test_reports_both_priors_and_does_not_hide_worsening():
    rows = [dict(prior='reno',doppler_error_km=2.,geometry_error_km=1.,change_km=-1.),
            dict(prior='sacramento',doppler_error_km=1.,geometry_error_km=3.,change_km=2.)]
    out = summarize(rows)
    assert out['reno']['improved'] == 1
    assert out['sacramento']['worsened'] == 1
    assert out['all']['geometry_mean_km'] > out['all']['doppler_mean_km']
    assert summarize([]) == {}


def test_stale_model_or_input_artifacts_fail_closed():
    entry=dict(session_id='s',cache_sha256='cache',input_manifest_sha256='input',analysis_manifest_sha256='analysis')
    result=dict(entry,branches={p:{'arms':{'D':{},'D_plus_geometry':{}}} for p in ('reno','sacramento')},
                protocol={'budget_per_arm':160},manifest_sha256='current')
    verify_result(result,entry,{'manifest_sha256':'current'})
    with pytest.raises(ValueError,match='cohort binding'):
        verify_result(result,entry,{'manifest_sha256':'stale'})
    result['cache_sha256']='wrong'
    with pytest.raises(ValueError,match='input binding'):
        verify_result(result,entry,{'manifest_sha256':'current'})


def test_partial_cohort_never_reads_reference_json_or_emits_distances(tmp_path,monkeypatch,capsys):
    import json
    import score_confirmation as scorer
    monkeypatch.setattr(scorer,'HERE',tmp_path)
    # Deliberately invalid JSON: partial gate must not parse this reference manifest.
    (tmp_path/'manifest.json').write_text('DO NOT PARSE REFERENCE COORDINATES')
    (tmp_path/'inventory.json').write_text(json.dumps([dict(session_id=str(i)) for i in range(4)]))
    scorer.main()
    output=json.loads(capsys.readouterr().out)
    assert output['complete'] is False and len(output['pending_sessions'])==4
    assert not (tmp_path/'distance_results.json').exists()
