import importlib.util,json,hashlib
from pathlib import Path
import pytest
HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("broad_evaluate",HERE/"evaluate.py"); assert SPEC and SPEC.loader
module=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(module)


def test_publication_gate_requires_all_64_attempts():
    units=[{"unit_id":f"U{i}"} for i in range(64)]
    records={(f"U{i}","merge128_to32"):{} for i in range(63)}
    with pytest.raises(ValueError,match="missing=1"): module.publication_gate(units,records)
    records[("U63","merge128_to32")]={}; module.publication_gate(units,records)


def test_load_records_verifies_seal_and_source(tmp_path):
    batch=tmp_path/"batch-01"; batch.mkdir(); source=tmp_path/"source.py"; source.write_text("x=1\n")
    receipt={"unit_id":"U1","arm":"merge128_to32","source_sha256":{str(source):module.sha256(source)}}
    path=batch/"U1-merge128_to32.json"; path.write_text(json.dumps(receipt))
    (batch/"U1-merge128_to32.seal.json").write_text(json.dumps({"prediction_sha256":module.sha256(path)}))
    assert module.load_records(tmp_path,"merge128_to32")[("U1","merge128_to32")]["_sealed"]
    source.write_text("changed\n")
    with pytest.raises(ValueError,match="source binding mismatch"): module.load_records(tmp_path,"merge128_to32")


def test_merging_failed_error_is_excluded_but_diagnostic_preserved():
    receipt={"status":"gate_failed","_sealed":True,"components":[{"weight":1.,"mean":[0.,0.]}],
             "checkpoints":[{"retained_mass_before_merging":.99,"projected_merge_score":.2,
             "projected_density_distortion":{"weighted_mean_absolute_log_error":.1,"maximum_absolute_log_error":1.}}],
             "planned_factors":2,"gate_failures":["projected_merge_score_above_0_1_nat"]}
    row=module.merging_row({"unit_id":"U","dataset":"DS9","session_id":"S"},receipt)
    assert row["error_km"] is None and row["highest_weight_component_error_km_diagnostic"] is not None
    assert row["materialized_component_cap"]==128 and row["retained_component_cap"]==32
