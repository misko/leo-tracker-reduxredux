import ast

import pytest

from leo.sky import propagation
from tools.pipeline_eval.qualification.catalog_bench_results import parity, timing
from tools.pipeline_eval.qualification.catalog_bench_worker import freeze_checksum


def test_staged_checksum_uses_only_its_frozen_source():
    source = """
_CHECKSUM_COLUMN = 68
ELEMENT_LINE_LENGTH = 69

def _validate_element_line(line, prefix, position):
    return element_line_checksum(line)

def parse_element_sets(text):
    return text

def element_line_checksum(line):
    return -1
"""
    candidate = (
        source
        + """
_CHECKSUM_TEST = bytes(128)

def element_line_checksum(line):
    return len(_CHECKSUM_TEST) + len(line[:_CHECKSUM_COLUMN])

raise AssertionError("unrelated top-level statements must remain inert")
"""
    )
    checksum, proof = freeze_checksum(source, candidate, propagation)
    assert checksum("123" * 40) == 196
    assert proof["support"] == ["_CHECKSUM_TEST"]
    assert proof["parser_source_equal"]
    assert proof["checksum_ast_sha256"] != proof["installed_checksum_ast_sha256"]

    changed_validator = candidate.replace("ELEMENT_LINE_LENGTH = 69", "ELEMENT_LINE_LENGTH = 68")
    with pytest.raises(ValueError, match="line validation source changed"):
        freeze_checksum(source, changed_validator, propagation)
    wrong_support = ast.unparse(ast.parse(candidate.replace("_CHECKSUM_TEST", "UNRELATED")))
    with pytest.raises(ValueError, match="unexpected checksum globals"):
        freeze_checksum(source, wrong_support, propagation)


def test_exact_parity_keeps_projection_count_and_both_geographic_arms():
    publication = dict(
        status="ok",
        arms={"c0": {"latlon": [1, 2]}, "fitted_c": {"latlon": [1, 3]}},
        metrics={"stage_s": {"initial": 28}, "compact_projections": 8},
    )
    preparation = dict(
        science="identical digest", provenance="source", checksum_calls=13, fallback_calls=0
    )
    leg = dict(
        publication=publication,
        numerical={"numerical": publication, "checksum_calls": 18, "fallback_calls": 0},
        preparation=preparation,
        service_result="success",
    )
    faster = publication | {"metrics": publication["metrics"] | {"stage_s": {"initial": 17}}}
    changed_projection = faster | {"metrics": faster["metrics"] | {"compact_projections": 9}}
    assert parity(dict(installed=leg, frozen_checksum=leg | {"publication": faster}))["exact"]
    reported = parity(
        dict(installed=leg, frozen_checksum=leg | {"publication": changed_projection})
    )
    assert reported["genuine_positions"] and not reported["exact"]
    timeout = parity(dict(installed=leg, frozen_checksum={"service_result": "timeout"}))
    assert timeout["exact"] is None and timeout["genuine_positions"] is False


def test_censored_leg_retains_completed_catalogue_work():
    data = {
        k: None
        for k in (
            "id",
            "branch",
            "role",
            "cpu",
            "service_result",
            "service_cpu_s",
            "service_wall_s",
            "memory_peak_mib",
            "cap_s",
        )
    }
    data.update(
        publication={"status": "timed_out"},
        preparation=dict(
            checksum_calls=13,
            clocks={
                "initial_sky": {"cpu_s": 2.0},
                "phase_history": {"cpu_s": 3.0},
                "native_preparation": {"checksum_calls": 13},
            },
        ),
    )
    row = timing(data)
    assert row["status"] == "timed_out"
    assert row["checksum_calls"] is None
    assert row["native_preparation_checksum_calls"] == 13
    assert row["causal_preparation_cpu_s"] == 5.0
    assert row["position_cpu_s"] is None
