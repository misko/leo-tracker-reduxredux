import hashlib
import json
from pathlib import Path

import algo03_runtime_release as release
import pytest
import stage_algo03_runtime as stage


def test_runtime_rejects_research_empty_mutated_and_unpinned_compositions(tmp_path):
    p = tmp_path/'kernel.py'
    p.write_text('tested implementation')
    manifest = tmp_path/'runtime-manifest.json'
    value = dict(kind=release.KIND, files_sha256={'kernel.py': release.digest(p)})
    manifest.write_text(json.dumps(value))
    pin = release.digest(manifest)
    assert release.verify(tmp_path, pin)['files_sha256']
    with pytest.raises(ValueError, match='pinned'):
        release.verify(tmp_path, '')
    p.write_text('changed')
    with pytest.raises(ValueError, match='member changed'):
        release.verify(tmp_path, pin)
    value['files_sha256'] = {}
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='empty'):
        release.verify(tmp_path, release.digest(manifest))
    value['kind'] = 'algo03-runtime-research-prototype-v1'
    value['files_sha256'] = {'kernel.py': release.digest(p)}
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='Unqualified'):
        release.verify(tmp_path, release.digest(manifest))
    value.update(kind=release.KIND, files_sha256={'../outside': '0'*64})
    manifest.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='member changed'):
        release.verify(tmp_path, release.digest(manifest))


def test_snapshot_patch_preserves_science_manifest_check_and_adds_exit_verification():
    original = '''    if manifest_hash != expected_hash:
        raise ValueError("Frozen ALGO03 manifest changed")
    for relative, expected in manifest["sha256"].items():
        if hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() != expected:
            raise ValueError("Frozen ALGO03 member changed: " + relative)
    child = launch()
    audit = check_read_audit(output, child.pid)
'''
    result = stage.snapshot_launcher(original)
    assert 'Frozen ALGO03 manifest changed' in result
    assert result.count('verify(ROOT)') == 2
    assert result.index('child = launch()') < result.rindex('verify(ROOT)')
    with pytest.raises(ValueError, match='Unexpected frozen'):
        stage.snapshot_launcher(original+original)


def test_qualification_binds_source_and_rejects_changed_science(monkeypatch):
    sources = {name: ('candidate '+name).encode() for name in stage.HIERARCHICAL_BASE}
    implementation = dict(files_sha256={name: hashlib.sha256(data).hexdigest()
                                        for name, data in sources.items()},
                          baseline_files_sha256=stage.HIERARCHICAL_BASE)
    rows = [dict(case=name, parity_path='proof-'+str(i), timing_paths=['timing'])
            for i, name in enumerate(('single', 'joint', 'single', 'two_family'))]
    documents = {
        stage.REPORT+'/implementation.json': implementation,
        stage.QUALIFICATION: dict(passed=True, scientific_tolerance=0,
                                  algo03_cases=rows[:2], algo07_cases=rows[2:]),
        str(Path(stage.QUALIFICATION).parent)+'/cache-fix.json':
            dict(runtime_manifest_sha256='b'*64),
        str(Path(stage.QUALIFICATION).parent)+'/receipts/saved-policy-parity.json':
            dict(passed=True, cases=175),
        str(Path(stage.QUALIFICATION).parent)+'/receipts/population-parity.json':
            dict(passed=True, results=[
            dict(passed=True, input_tensors_and_output_values_exact=True)]*16),
        'timing': dict(successful_execution=True, timed_out=False,
                       reference_after=dict(verified=True)),
    }
    documents.update({row['parity_path']: dict(passed=True, differences=[], exact_leaves=12,
                      candidate_runtime_manifest_sha256='b'*64,
                      both_calibration_arms_required=True, tolerance=0) for row in rows})

    def committed(repo, revision, name):
        return sources[name] if name in sources else json.dumps(documents[name]).encode()

    monkeypatch.setattr(stage, 'committed', committed)
    baseline = dict(files_sha256=stage.HIERARCHICAL_BASE)
    actual, _ = stage.qualified_sources('.', 'a'*40, baseline)
    assert actual == sources
    first = next(iter(sources))
    sources[first] += b' untested'
    with pytest.raises(ValueError, match='source differs'):
        stage.qualified_sources('.', 'a'*40, baseline)
    sources[first] = ('candidate '+first).encode()
    documents['proof-1']['differences'] = [{'objective': .001}]
    with pytest.raises(ValueError, match='parity failed'):
        stage.qualified_sources('.', 'a'*40, baseline)
    documents['proof-1']['differences'] = []
    documents['proof-1']['both_calibration_arms_required'] = False
    with pytest.raises(ValueError, match='Paired exact'):
        stage.qualified_sources('.', 'a'*40, baseline)
    documents['proof-1']['both_calibration_arms_required'] = True
    documents['proof-1']['candidate_runtime_manifest_sha256'] = 'c'*64
    with pytest.raises(ValueError, match='Paired exact'):
        stage.qualified_sources('.', 'a'*40, baseline)


def test_cache_fix_requires_separately_bound_old_and_new_bytes(monkeypatch):
    old, new = b'previous qualified cache', b'corrected cache'
    proof = dict(file=stage.CACHE_SOURCE,
                 previous_sha256=hashlib.sha256(old).hexdigest(),
                 sha256=hashlib.sha256(new).hexdigest(), regression_tests_passed=True)
    monkeypatch.setattr(stage, 'committed', lambda repo, revision, name:
                        new if name == stage.CACHE_SOURCE else json.dumps(proof).encode())
    prepared = {stage.CACHE_SOURCE: old}
    overrides, _ = stage.qualified_cache_fix('.', 'a'*40, prepared)
    assert overrides == {stage.CACHE_SOURCE: new}
    for key, value in [('previous_sha256', '0'*64), ('sha256', '0'*64),
                       ('regression_tests_passed', False)]:
        previous = proof[key]
        proof[key] = value
        with pytest.raises(ValueError, match='Cache fix differs'):
            stage.qualified_cache_fix('.', 'a'*40, prepared)
        proof[key] = previous
