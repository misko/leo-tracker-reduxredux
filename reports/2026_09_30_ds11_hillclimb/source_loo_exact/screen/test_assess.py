"""Exercise cached atomic normalization and complete variable-sized selection."""
import importlib.util
import json
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("ds11_screen_assess_tests", Path(__file__).with_name("assess.py"))
assess = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(assess)


@pytest.mark.parametrize("mode", ("complete", "unqualified", "coverage"))
def test_atomic_cache_variable_fold_selection_requires_every_family(tmp_path, monkeypatch, mode):
    monkeypatch.setattr(assess, "HERE", tmp_path)
    jobs = []
    for family_index, family in enumerate(assess.FAMILIES):
        for norad in (101, 102):
            key = f"04_{family}_{norad}"
            track_ids = [f"a{norad}", f"b{norad}"]
            affected = family_index == 0 and norad == 101
            qualified = not (mode == "unqualified" and affected)
            fold = dict(norad=norad, track_ids=track_ids, x=[1.0, -2.0, 0.1],
                        retained_score=-10.0, common_held_score=-100.0 + family_index,
                        held_observation_count=4 if mode == "coverage" and affected else 3,
                        optimizer=dict(qualified=qualified, success=qualified, boundary=False,
                                       gradient_max_abs=0.0, gradient_audit_max_abs=0.0))
            record = dict(index=4, family=family, job_key=key, full_endpoint_x=[0.0, 0.0, 0.0],
                          reference_used=False, fold=fold, sources={})
            path = tmp_path / f"{key}.json"
            path.write_text(json.dumps(record))
            jobs.append(dict(index=4, family=family, norad=norad, source_track_ids=track_ids,
                             full_endpoint_x=[0.0, 0.0, 0.0], cache=dict(kind="atomic", path=str(path))))
    (tmp_path / "plan.json").write_text(json.dumps(dict(
        schema="ds11-source-loo-exact-screen-plan/v1", jobs=jobs, sources={})))
    assess.main(4)
    selection = json.loads((tmp_path / "selections" / "04.json").read_text())
    assert selection["planned_folds"] == 8
    assert selection["cached_folds"] == 8
    assert selection["qualified_folds"] == (7 if mode == "unqualified" else 8)
    assert selection["selectable"] == (mode == "complete")
    assert selection["selected_family"] == ("robust_t4_scale200" if mode == "complete" else None)
    assert all(len(family["coverage"]) == 2 for family in selection["families"])
