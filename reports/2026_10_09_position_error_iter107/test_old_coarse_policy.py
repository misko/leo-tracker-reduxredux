"""Synthetic metadata tests; no recording or optimizer use."""

import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "old_coarse_policy", Path(__file__).with_name("old_coarse_policy.py")
)
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


def inputs():
    current = dict.fromkeys(policy.OLD, "sha256:current")
    current["analysis/hard60_score.py"] = "sha256:unchanged"
    old = dict(current, **policy.OLD)
    config = dict(
        levels_km=[40, 20, 10, 5], slope_half_width_hz_s=60, recovery_policy="failed-coarse-box-v1"
    )
    previous = {k: v for k, v in config.items() if k != "recovery_policy"}
    return old, current, previous, config


def test_exact_known_pair_is_metadata_only_not_blanket_reuse():
    args = inputs()
    result = policy.eligibility(*args)
    assert result["metadata_eligible"] and not result["reuse_authorized"]
    assert "final" in result["forbidden_aliases"]
    assert (
        "finite feasible state and saved objective agreement" in result["required_runtime_checks"]
    )


@pytest.mark.parametrize("change", ["oldhash", "physical", "missing", "extra", "config", "policy"])
def test_rejects_other_versions_dependencies_and_configuration(change):
    old, current, previous, config = inputs()
    if change == "oldhash":
        old[next(iter(policy.OLD))] = "sha256:another-version"
    elif change == "physical":
        old["analysis/hard60_score.py"] = "sha256:changed"
    elif change == "missing":
        old.pop("analysis/hard60_score.py")
    elif change == "extra":
        old["analysis/unknown.py"] = "sha256:unknown"
    elif change == "config":
        previous["slope_half_width_hz_s"] = 30
    else:
        config["recovery_policy"] = "off"
    assert not policy.eligibility(old, current, previous, config)["metadata_eligible"]


def test_only_renderer_may_differ_and_inputs_unchanged():
    old, current, previous, config = inputs()
    old[policy.PRESENTATION] = "sha256:old-renderer"
    current[policy.PRESENTATION] = "sha256:new-renderer"
    assert policy.eligibility(old, current, previous, config)["metadata_eligible"]
    assert "recovery_policy" not in previous
