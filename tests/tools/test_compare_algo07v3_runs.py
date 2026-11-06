import copy
import json
from types import SimpleNamespace

import compare_algo07v3_runs as comparison
import numpy as np
import pytest
from compare_algo07v3_runs import matched_requests, module_changes, scientific_values


def test_only_output_destination_may_change_between_requests():
    a = dict(output_root="/old", execution_policy="validation-all-work", prior=[1.0, 2.0])
    b = dict(a, output_root="/new")
    matched_requests(a, b)
    with pytest.raises(ValueError):
        matched_requests(a, a)
    with pytest.raises(ValueError):
        matched_requests(a, dict(b, prior=[1.0, 2.00001]))
    with pytest.raises(ValueError):
        matched_requests(a, dict(b, surprise=True))


def test_non_audit_evidence_and_stage_inventory_are_not_omitted():
    a = dict(
        preparation=dict(x=np.array([1.0])),
        selected=dict(owners={"p": 12}),
        stage_timings=[dict(stage="initial", seconds=1.0)],
        audit={},
        presentation={},
        provenance={},
    )
    b = copy.deepcopy(a)
    b["stage_timings"][0]["seconds"] = 3.0
    scientific_values(a, b)
    for key, value in (
        ("preparation", dict(x=np.array([1.000000001]))),
        ("selected", dict(owners={"p": 13})),
        ("stage_timings", [dict(stage="initial", seconds=1.0, unreviewed=True)]),
        ("stage_timings", []),
    ):
        with pytest.raises(ValueError):
            scientific_values(a, dict(b, **{key: value}))


def test_only_declared_loaded_source_changes_and_additions_are_allowed():
    a = dict(job='old', science='same')
    b = dict(job='new', science='same', executor='added')
    assert module_changes(a, b, ['job'], ['executor']) == ({'job'}, {'executor'})
    for changed in (dict(b, science='changed'), dict(b, unexpected='added'), {'job': 'new'}):
        with pytest.raises(ValueError):
            module_changes(a, changed, ['job'], ['executor'])
    with pytest.raises(ValueError):
        module_changes(a, b, ['job'], [])


def test_explicit_empty_source_declaration_is_distinct_from_default():
    name = 'leo.analysis.localization_v3.hierarchical'
    original = {name: 'old', 'other': 'same'}
    changed = dict(original, **{name: 'new'})
    assert module_changes(original, original, [], []) == (set(), set())
    assert module_changes(original, changed, None, []) == ({name}, set())
    with pytest.raises(ValueError, match='Declared source changes'):
        module_changes(original, changed, [], [])
    with pytest.raises(ValueError, match='Declared source changes'):
        module_changes(original, original, None, [])


def test_scientific_match_does_not_waive_missing_supervisor_clock(monkeypatch, tmp_path):
    request = tmp_path / 'request.json'
    request.write_text(json.dumps(dict(output_root='unused')))
    monkeypatch.setattr(comparison, 'compare_science', lambda args: {'science': True})
    args = SimpleNamespace(baseline_request=request, candidate_request=request,
                           baseline_timing=tmp_path / 'missing',
                           candidate_timing=tmp_path / 'missing')
    with pytest.raises(FileNotFoundError):
        comparison.compare(args)


def test_scientific_match_does_not_waive_failed_execution(monkeypatch, tmp_path):
    request, clock = tmp_path / 'request.json', tmp_path / 'clock.json'
    request.write_text('{}')
    clock.write_text(json.dumps(dict(status='exited', returncode=124)))
    monkeypatch.setattr(comparison, 'compare_science', lambda args: {'science': True})
    args = SimpleNamespace(baseline_request=request, candidate_request=request,
                           baseline_timing=clock, candidate_timing=clock)
    with pytest.raises(ValueError, match='Fresh completed'):
        comparison.compare(args)
