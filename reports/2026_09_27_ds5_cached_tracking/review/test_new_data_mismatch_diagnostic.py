import importlib.util
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("mismatch_diagnostic", HERE / "run_new_data_mismatch_diagnostic.py")
module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = module
SPEC.loader.exec_module(module)


def obs(window=0, epoch=100.25, cfo=1000, exact=.4, control=.01, supported=True):
    return module.Observation(window, epoch, cfo, exact, control, supported)


def test_comparison_uses_cross_window_frame_lattice_and_positive_gate():
    cached = obs(window=0, epoch=100.25)
    same_lattice = obs(window=4, epoch=100.25, cfo=8500)
    result = module.comparison(cached, same_lattice, 2_500_000)
    assert result["positive_match"] and result["timing_error_us"] < 1e-9
    margin_fail = obs(window=4, epoch=100.25, cfo=8500, exact=.02, control=.01)
    result = module.comparison(cached, margin_fail, 2_500_000)
    assert result["coordinate_match"] and not result["positive_match"]


def test_mismatch_selection_requires_accepted_cache_positive():
    row = {"case_id":"case", "rx":1, "reason":"cache_hit", "matched_reference":False,
           "reference":{"supported":True,"exact":.4,"control":.01},
           "observation":{"supported":True,"exact":.3,"control":.01}}
    assert list(module.mismatches({"rows":[row]})) == [("case",1)]
    row["reason"]="failed_prediction"
    try:
        module.mismatches({"rows":[row]})
    except ValueError as error:
        assert "accepted cached positive" in str(error)
    else:
        raise AssertionError("non-cache mismatch was accepted")
