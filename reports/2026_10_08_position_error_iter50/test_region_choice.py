"""Selection gates and preservation of a real sep25 regional rescue."""

import copy
import json
from pathlib import Path

from region_choice import select_documents

REPORTS = Path(__file__).resolve().parent.parent


def doc(fitted, zero):
    return {
        "methods": [
            {"arms": [dict(name="fitted-c", selected=fitted), dict(name="zero-c", selected=zero)]}
        ]
    }


def test_real_sep25_rescue_is_preserved_when_new_set_ties():
    baseline = json.loads(
        (REPORTS / "2026_10_08_position_error_iter01/baseline/DS17-008.json").read_text()
    )
    sep25 = json.loads(
        (
            REPORTS / "2026_10_08_position_error_iter06/results/DS17-008/separation-25.json"
        ).read_text()
    )
    _, sources = select_documents(dict(baseline=baseline, sep25=sep25, sep50=copy.deepcopy(sep25)))
    assert sources == {"fitted-c": "sep25", "zero-c": "sep25"}


def test_each_arm_selects_by_eligible_score_never_position_error():
    base = dict(selection_score=10, converged=True, horizontal_error_m=1)
    fit25 = dict(selection_score=9, converged=True, horizontal_error_m=100000)
    failed = dict(selection_score=1, converged=False, horizontal_error_m=0)
    zero50 = dict(selection_score=8, converged=True, horizontal_error_m=200000)
    chosen, sources = select_documents(
        dict(baseline=doc(base, base), sep25=doc(fit25, base), sep50=doc(failed, zero50))
    )
    assert sources == {"fitted-c": "sep25", "zero-c": "sep50"}
    assert chosen["fitted-c"] == fit25
    assert chosen["zero-c"] == zero50
