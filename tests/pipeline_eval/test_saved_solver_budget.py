from importlib import import_module

import pytest


trial = import_module("reports.ALGO08.single-core-2x.saved_solver_budget")


def test_cpu_estimate_replaces_only_the_prior_solver_time():
    result = trial.budget(120, 65, 20, 25)
    assert result == dict(estimated_outer_cpu_s=45, solver_budget_for_2x_cpu_s=15,
                          estimated_total_cpu_s=70, estimated_seconds_above_half=10)
    for old in (0, 65, 100, float("nan")):
        with pytest.raises(ValueError):
            trial.budget(120, 65, old, 25)


def test_outer_options_match_library_contents_and_capture_source_but_allow_another_solver():
    source = "tools/pipeline_eval/variants/experimental/receiver_ingress.py"
    pin = dict(library="parent/receiver.so", sha256="original")
    spec = dict(sources={source: "digest"}, detector_sha256="detector", solver="old", paired_sha256=pin)
    equal = dict(spec, solver="new", paired_sha256=dict(pin, library="successor/receiver.so"))
    assert trial.outer_options(spec) == trial.outer_options(equal)
    assert trial.outer_options(spec) != trial.outer_options(dict(equal, sources={source: "changed"}))
    assert trial.outer_options(spec) != trial.outer_options(dict(equal, detector_sha256="different"))
