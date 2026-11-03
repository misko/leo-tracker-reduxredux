import hashlib
import json

import numpy as np
import pytest

from evaluate import (ecdf_with_failures, evaluate, load_attempt_records, load_pipeline_context,
                      load_verified_receipts, pipeline_context_row, selected_units,
                      summarize_pipeline_context, require_complete_attempt_panel)
from plots import generate_summary_figures, spatial_mixture_relative_density


def _selection():
    rows=[]
    for dataset,count in (("DS9",22),("DS10",21),("DS11",21)):
        rows += [{"dataset":dataset,"unit_id":f"{dataset}-F{i:03}","session_id":f"s-{dataset}-{i}"} for i in range(count)]
    return {"units":rows}


def _receipt(unit, arm, status="complete", error_east=0.):
    return {"unit_id":unit["unit_id"],"session_id":unit["session_id"],"arm":arm,"status":status,
            "prior_name":"sacramento_uniform",
            "components":[{"weight":1.,"mean":[error_east,0.],"covariance":np.eye(2).tolist()}],
            "checkpoints":[{"retained_mass":.98}],"selection":{"retained_tracks":2},
            "wall_seconds":1.,"gate_failures":[],
            "prior_point_estimate":{"latitude_deg":38.5816,"longitude_deg":-121.4944,
                                    "rule":"center_of_intended_uniform_disk"},
            "config":{"physics":{"prior_center_lat_deg":38.5816,"prior_center_lon_deg":-121.4944},
                      "spatial_prior":{"component_count":32,"intended_radius_km":250.0,
                       "approximation":"equal_area_annular_sector_cell_moment_gaussians",
                       "represented_mass_outside_intended_disk":.025}}}


def test_selection_enforces_frozen_counts():
    assert len(selected_units(_selection())) == 64
    bad=_selection(); bad["units"].pop()
    with pytest.raises(ValueError,match="64"):
        selected_units(bad)


def test_publication_refuses_partial_or_extra_attempt_panel():
    selection=_selection(); units=selected_units(selection)
    receipts={(unit["unit_id"],arm):_receipt(unit,arm) for unit in units for arm in ("gaussian_sum","greedy","prior_only")}
    require_complete_attempt_panel(selection,receipts)
    receipts.pop((units[0]["unit_id"],"greedy"))
    with pytest.raises(ValueError,match="missing=1"):
        require_complete_attempt_panel(selection,receipts)


def test_all_planned_attempts_remain_in_denominator_and_pairs_require_completion():
    selection=_selection(); units=selected_units(selection); receipts={}
    for unit in units:
        receipts[(unit["unit_id"],"prior_only")]=_receipt(unit,"prior_only")
    receipts[(units[0]["unit_id"],"gaussian_sum")]=_receipt(units[0],"gaussian_sum",error_east=.1)
    receipts[(units[0]["unit_id"],"greedy")]=_receipt(units[0],"greedy",error_east=.2)
    receipts[(units[1]["unit_id"],"gaussian_sum")]=_receipt(units[1],"gaussian_sum",status="gate_failed")
    result=evaluate(selection,receipts)
    assert len(result["rows"]) == 192
    assert result["summaries"]["pooled"]["gaussian_sum"]["status_counts"] == {"complete":1,"gate_failed":1,"missing":62}
    assert result["summaries"]["pooled"]["gaussian_sum"]["attempted_count"] == 2
    failed=next(row for row in result["rows"] if row["unit_id"]==units[1]["unit_id"] and row["arm"]=="gaussian_sum")
    assert failed["error_km"] is None and failed["highest_weight_component_error_km"] is not None
    assert len(result["paired_completed_gaussian_sum_greedy"]) == 1
    assert result["summaries"]["pooled"]["prior_only"]["sub_km_fraction_all_planned"] == 0.
    assert result["prior_center_error_km"] > 100.


def test_failure_aware_ecdf_never_reaches_one_with_failures():
    rows=[{"completed":True,"error_km":.2},{"completed":True,"error_km":1.2},{"completed":False,"error_km":.1}]
    x,y=ecdf_with_failures(rows,3)
    np.testing.assert_allclose(x,[.2,1.2]); np.testing.assert_allclose(y,[1/3,2/3])


def test_native_seal_is_required(tmp_path):
    folder=tmp_path/"batch-01"; folder.mkdir(); receipt=folder/"x.json"; receipt.write_text(json.dumps({"unit_id":"u","arm":"greedy"}))
    digest="sha256:"+hashlib.sha256(receipt.read_bytes()).hexdigest()
    (folder/"x.seal.json").write_text(json.dumps({"prediction_sha256":digest}))
    assert ("u","greedy") in load_verified_receipts(tmp_path)
    receipt.write_text("{}")
    with pytest.raises(ValueError,match="seal mismatch"):
        load_verified_receipts(tmp_path)


def test_launch_only_timeout_is_attempted_failure_not_missing(tmp_path):
    folder=tmp_path/"batch-01"; folder.mkdir()
    launch={"unit_id":"DS9-F000","arm":"gaussian_sum","status":"timeout","wall_seconds":90.1,
            "native_progress_exists":True,"returncode":124}
    (folder/"x.launch.json").write_text(json.dumps(launch))
    records=load_attempt_records(tmp_path)
    row=evaluate(_selection(),records)["rows"][0]
    assert row["attempted"] and not row["completed"] and row["status"] == "timeout"
    assert row["progress_diagnostic_available"] and row["error_km"] is None


def test_launcher_runtime_is_joined_to_sealed_native_runtime(tmp_path):
    folder=tmp_path/"batch-01"; folder.mkdir(); unit=selected_units(_selection())[0]
    receipt=_receipt(unit,"greedy"); receipt_path=folder/"x.json"
    receipt_path.write_text(json.dumps(receipt)); digest="sha256:"+hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    (folder/"x.seal.json").write_text(json.dumps({"prediction_sha256":digest}))
    (folder/"x.launch.json").write_text(json.dumps({"unit_id":unit["unit_id"],"arm":"greedy",
                                                     "status":"complete","wall_seconds":2.5}))
    row=evaluate(_selection(),load_attempt_records(tmp_path))["rows"][1]
    assert row["native_pre_artifact_runtime_s"] == 1.
    assert row["launcher_runtime_s"] == 2.5 and row["runtime_s"] == 2.5


def test_summary_plots_accept_failure_only_dynamic_arms(tmp_path):
    result=evaluate(_selection(),{})
    paths=generate_summary_figures(result,tmp_path)
    assert len(paths)==4 and all(path.stat().st_size>1000 for path in paths)


def test_historical_plot_keeps_unmatched_context_visibly_separate(tmp_path):
    result=evaluate(_selection(),{})
    result["historical_pipeline_context"]={"rows":[
        {"status":"incomplete","error_km":5.} for _ in range(64)
    ]}
    paths=generate_summary_figures(result,tmp_path)
    assert any(path.name == "historical-pipeline-context.png" for path in paths)


def test_spatial_mixture_density_uses_all_weighted_components():
    east,north=np.meshgrid(np.array([-10.,10.]),np.array([0.]))
    components=[
        {"weight":.75,"mean_en_km":[-10.,0.],"covariance_en_km2":[[1.,0.],[0.,1.]]},
        {"weight":.25,"mean_en_km":[10.,0.],"covariance_en_km2":[[1.,0.],[0.,1.]]},
    ]
    density=spatial_mixture_relative_density(components,east,north)
    assert density[0,0] == pytest.approx(1.)
    assert density[0,1] == pytest.approx(1/3)


def test_pipeline_context_recomputes_error_and_is_explicitly_unmatched():
    unit={"dataset":"DS9","unit_id":"DS9-F001","session_id":"s"}
    document={"session_id":"s","manifest":{"document":{"priors":[
        {"name":"sacramento","search_complete":True,
         "selected":{"latitude_deg":37.849056280893684,"longitude_deg":-122.48575489722863}}
    ]}}}
    row=pipeline_context_row(document,{"s":unit})
    assert row["error_km"] == pytest.approx(0.)
    assert "unmatched" in row["comparison"] and "different tracks" in row["qualification"]


def test_pipeline_context_preserves_incomplete_and_fetch_failure(tmp_path):
    units=selected_units(_selection())
    unit=units[0]
    document={"session_id":unit["session_id"],"manifest":{"document":{"priors":[
        {"name":"sacramento","search_complete":False,
         "selected":{"latitude_deg":37.849056280893684,"longitude_deg":-122.48575489722863}}
    ]}}}
    (tmp_path/f"{unit['unit_id']}.json").write_text(json.dumps(document))
    second=units[1]
    (tmp_path/f"{second['unit_id']}.fetch-error.json").write_text(json.dumps({"error":"TimeoutError"}))
    rows=load_pipeline_context(tmp_path,units)
    assert rows[0]["status"] == "incomplete" and rows[0]["error_km"] == pytest.approx(0.)
    assert rows[1]["status"] == "fetch_error" and rows[1]["error_km"] is None
    summary=summarize_pipeline_context(rows,64)
    assert summary["selected_point_count"] == 1
    assert summary["status_counts"] == {"fetch_error":1,"incomplete":1,"missing":62}
