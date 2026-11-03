import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("final_screen_test", Path(__file__).with_name("final_assess.py"))
final = importlib.util.module_from_spec(spec)
spec.loader.exec_module(final)


@pytest.mark.parametrize("terminal", (False, True))
def test_no_geographic_scoring_for_incomplete_or_failed_screen(tmp_path, monkeypatch, terminal):
    monkeypatch.setattr(final, "HERE", tmp_path)
    monkeypatch.setattr(final, "geographic_outcome", lambda *a: pytest.fail("geography read too early"))
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(dict(screen_indices=list(range(0,32,4)), sources={})))
    if not terminal:
        with pytest.raises(ValueError, match="incomplete"):
            final.main()
        assert not (tmp_path / "outcome.json").exists()
        return
    (tmp_path / "selections").mkdir()
    (tmp_path / "selections" / "00.json").write_text(json.dumps(dict(
        schema="ds11-source-loo-recovery-screen-selection/v1", index=0, reference_used=False,
        selectable=False, selected_family=None, planned_folds=4, qualified_folds=3,
        cached_folds=0, sources={str(path):final.digest(path)})))
    final.main()
    result=json.loads((tmp_path / "outcome.json").read_text())
    assert len(result["scans"])==8 and not result["geographic_errors_evaluated"]
    assert not result["advancement_gate_passed"]


def test_geographic_gate_scores_existing_full_endpoints(tmp_path, monkeypatch):
    here = tmp_path / "experiment" / "screen_recovery"
    here.mkdir(parents=True)
    monkeypatch.setattr(final, "HERE", here)
    (tmp_path / "harness.py").write_text(
        "REFERENCE=(0,0)\ndef distance(point): return point[0]\n"
        "def percentile(values,q): return sorted(values)[-1]\n")
    rows=[]; scans=[]; jobs=[]; bindings={}
    for index in range(8):
        paths={}
        for family,error,x in (("iid_t4_scale100",10,[0.,0.,0.]),
                               ("robust_t4_scale200",7,[1.,1.,0.])):
            path=here/f"{index}_{family}.json"
            path.write_text(json.dumps(dict(selected=dict(qualified=True,x=x,
                                                          estimate_deg=[error,0]))))
            paths[family]=str(path)
            bindings[str(path)]=final.digest(path)
            jobs.append(dict(index=index,family=family,full_endpoint_x=x))
        scans.append(dict(index=index,endpoint_paths=paths))
        rows.append(dict(index=index,selectable=True,selected_family="robust_t4_scale200"))
    plan=dict(scans=scans,jobs=jobs,sources=bindings,selection=dict(geographic_gate=dict(
        minimum_wins_over_iid=5,minimum_median_error_reduction_fraction=.10)))
    outcome=final.geographic_outcome(plan,rows,{})
    assert outcome["advancement_gate_passed"] and outcome["wins"]==8
    assert outcome["selected"]["median_m"]==7 and outcome["iid"]["median_m"]==10
