import hashlib
import json

import algo07_runtime_release as release
import pytest
import stage_algo07_runtime as stage


def test_runtime_requires_pinned_manifest_and_unchanged_members(tmp_path):
    source = tmp_path/'kernel.py'
    source.write_text('qualified source')
    manifest = tmp_path/'runtime-manifest.json'
    manifest.write_text(json.dumps(dict(kind='algo07-qualified-runtime-composition-v1',
                                        files_sha256={'kernel.py':release.digest(source)})))
    expected = release.digest(manifest)
    assert release.verify(tmp_path, expected)['files_sha256']
    with pytest.raises(ValueError, match='pinned'):
        release.verify(tmp_path, '')
    source.write_text('changed source')
    with pytest.raises(ValueError, match='member changed'):
        release.verify(tmp_path, expected)
    with pytest.raises(ValueError, match='manifest changed'):
        release.verify(tmp_path, '0'*64)


def test_runtime_rejects_escape_even_in_pinned_manifest(tmp_path):
    manifest = tmp_path/'runtime-manifest.json'
    manifest.write_text(json.dumps(dict(kind='algo07-qualified-runtime-composition-v1',
                                        files_sha256={'../escaped':'0'*64})))
    with pytest.raises(ValueError, match='member changed'):
        release.verify(tmp_path, release.digest(manifest))


def test_staging_checks_qualification_and_preserves_base(tmp_path, monkeypatch):
    base = tmp_path/'base'
    kernel = base/stage.KERNEL
    kernel.parent.mkdir(parents=True)
    kernel.write_bytes(b'reference')
    baseline = dict(revision=stage.BASE_REVISION,
                    files_sha256={stage.KERNEL:release.digest(kernel)})
    (base/'release-manifest.json').write_text(json.dumps(baseline))
    monkeypatch.setattr(stage, 'BASE_MANIFEST_SHA256', release.digest(base/'release-manifest.json'))
    monkeypatch.setattr(stage, 'REFERENCE_KERNEL_SHA256', release.digest(kernel))
    monkeypatch.setattr(stage, 'CANDIDATE_KERNEL_SHA256', hashlib.sha256(b'candidate').hexdigest())
    files = {
        stage.KERNEL: b'candidate', 'tools/algo07_runtime_worker.py': b'wrapper',
        'tools/algo07_runtime_release.py': b'verifier', stage.REPORT+'/protocol.json': b'{}',
        stage.REPORT+'/full-replay-parity.json': b'{"passed":true,"differing_floats":0}',
        stage.REPORT+'/population-reconstruction.json': json.dumps(dict(
            passed=True, results=[{}]*16)).encode(),
        stage.REPORT+'/policy-parity.json': b'{"passed":true,"cases":175}',
    }
    monkeypatch.setattr(stage, 'committed', lambda repo, revision, path: files[path])
    plan = stage.stage(tmp_path, 'a'*40, base)
    assert plan['numerical_override'] == stage.KERNEL
    assert not plan['service_mutation']
    assert kernel.read_bytes() == b'reference'
    files[stage.REPORT+'/full-replay-parity.json'] = b'{"passed":false,"differing_floats":0}'
    with pytest.raises(ValueError, match='qualification'):
        stage.stage(tmp_path, 'a'*40, base)
    files[stage.KERNEL] = b'untested'
    with pytest.raises(ValueError, match='qualified numerical trial'):
        stage.stage(tmp_path, 'a'*40, base)


def test_prepared_qualification_binds_every_source_to_exact_full_replays(monkeypatch):
    sources = {name: name.encode() for name in stage.PREPARED_FILES}
    documents = {
        'protocol.json': {},
        'implementation.json': dict(
            default_cache_size=1,
            files_sha256={name: hashlib.sha256(data).hexdigest()
                          for name, data in sources.items()},
            baseline_files_sha256={name: None for name in sources}),
        'full-replays.json': dict(passed=True, cases=[dict(
            case=case, parity=dict(passed=True, differing_floats=0),
            read_audit_verified=True, frozen_inputs_verified=True)
            for case in ('fresh-fallback', 'slow-additive')]),
        'population-parity.json': dict(passed=True, results=[dict(
            passed=True, input_tensors_and_output_values_exact=True)]*16),
        'policy-parity.json': dict(passed=True, cases=175),
    }

    def committed(repo, revision, path):
        if path in sources:
            return sources[path]
        return json.dumps(documents[path.removeprefix(stage.PREPARED_REPORT+'/')]).encode()

    monkeypatch.setattr(stage, 'committed', committed)
    actual, proofs = stage.prepared_qualification('.', 'a'*40, dict(files_sha256={}))
    assert actual == sources and len(proofs) == 5
    name = stage.PREPARED_FILES[0]
    sources[name] += b'untested'
    with pytest.raises(ValueError, match='source differs'):
        stage.prepared_qualification('.', 'a'*40, dict(files_sha256={}))
    sources[name] = name.encode()
    documents['full-replays.json']['cases'][0]['parity']['differing_floats'] = 1
    with pytest.raises(ValueError, match='qualification is incomplete'):
        stage.prepared_qualification('.', 'a'*40, dict(files_sha256={}))
