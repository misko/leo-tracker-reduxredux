from copy import deepcopy

import pytest

from tools.pipeline_eval.qualification import new_waveforms as study
from tools.pipeline_eval.qualification import new_waveforms_lighter as lighter


def test_new_trial_context_leaves_the_previous_study_intact():
    earlier_report = study.previous.REPORT
    earlier_reference = study.reference.REPORT
    with study.context():
        assert study.previous.REPORT == study.REPORT
        assert study.reference.REPORT == study.REPORT
        assert study.previous.METHOD == study.METHOD
        assert study.reference.MODULE == study.MODULE
    assert earlier_report == study.previous.REPORT
    assert earlier_reference == study.reference.REPORT


def qualified():
    gate = dict(
        entry="leo_native_glrt_analyze_center_union_v1",
        passed=True,
        exact_edges=["lower", "upper"],
        candidate_rows_exact=True,
        support_and_gates_exact=True,
        baseline_sha256="a" * 64,
        candidate={"sha256": "d" * 64},
        scout={"sha256": "b" * 64},
    )
    plan = {"detectors": {"candidate": {"sha256": "a" * 64}, "scout": {"sha256": "b" * 64}}}
    return gate, plan


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("entry", "typed-only"),
        ("baseline_sha256", "c" * 64),
        ("candidate", {"sha256": "a" * 64}),
        ("passed", False),
        ("exact_edges", ["upper"]),
        ("candidate_rows_exact", False),
        ("support_and_gates_exact", False),
        ("scout", {"sha256": "c" * 64}),
    ],
)
def test_third_arm_rejects_incomplete_direct_scientific_gate(field, value):
    gate, plan = qualified()
    lighter.validate_gate(gate, plan)
    incomplete = deepcopy(gate)
    incomplete[field] = value
    with pytest.raises(ValueError, match="independent scientific parity"):
        lighter.validate_gate(incomplete, plan)
