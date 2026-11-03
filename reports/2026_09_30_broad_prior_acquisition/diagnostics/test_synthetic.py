import importlib.util
from pathlib import Path
HERE=Path(__file__).resolve().parent
SPEC=importlib.util.spec_from_file_location("synthetic_diagnostic",HERE/"synthetic.py")
assert SPEC and SPEC.loader
module=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(module)


def test_independent_clean_case_selects_known_identity():
    result=module.evaluate(); scores={x["candidate"]:x["log_joint"] for x in result["candidates"]}
    assert result["generator_uses_likelihood_prediction_callback"] is False
    assert result["best_label"] == result["known_candidate"] == "70001"
    assert scores["70001"] > scores["70002"] and scores["70001"] > result["background_log_joint"]


def test_large_unmodeled_outlier_selects_background():
    assert module.evaluate(20_000.)["best_label"] == "background"
