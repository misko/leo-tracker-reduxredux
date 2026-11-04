import hashlib
import json
from types import SimpleNamespace

import compare_algo07v3_initial_inputs as compare
import numpy as np
import pytest


def fixture(tmp_path):
    ref, cand = tmp_path/'reference', tmp_path/'candidate'
    source, prior = ref/'worker/inference/SCAN', ref/'worker/inference/causal_prior/SCAN'
    for path in (source, prior, cand):
        path.mkdir(parents=True)

    def write(path, doc):
        path.write_text(json.dumps(doc))

    noise_source = tmp_path/'noise.py'
    noise_source.write_text('original source')
    observations = [dict(observation_id='a', measured_cfo_hz=1.)]
    tracks = [dict(observation_ids=['a'], coefficients=[1., 2.])]
    metadata = dict(cutoff=123)
    write(source/'tracking.json', {})
    for name, doc in [('observations', observations), ('tracks', tracks),
                      ('prepared', dict(metadata=metadata)), ('receipt', metadata),
                      ('nominal_elements', {'1': 'elements'}), ('previous_receipt', {})]:
        write(source/(name+'.json'), doc)
    write(source/'radio_noise.json', dict(sigma=150., code_sha256=compare.digest(noise_source),
          source_sha256={n+'.json':compare.digest(source/(n+'.json'))
                         for n in ('observations', 'tracks')}))
    write(prior/'previous_receipt.json', {})
    for folder, name in [(source, 'selected.tle'), (source, 'previous.tle'),
                         (prior, 'previous.tle')]:
        (folder/name).write_text('reference TLE bytes')
    for name, path in [('selected.tle', source/'selected.tle'),
                       ('previous.tle', source/'previous.tle'),
                       ('genuine_previous.tle', prior/'previous.tle'),
                       ('nominal_elements.json', source/'nominal_elements.json'),
                       ('previous_receipt.json', source/'previous_receipt.json'),
                       ('genuine_previous_receipt.json', prior/'previous_receipt.json')]:
        (cand/name).write_bytes(path.read_bytes())
    write(cand/'tracks.json', dict(observations=observations, tracks=tracks, metadata=metadata))
    write(cand/'radio_noise.json', dict(sigma=150.))
    write(cand/'metadata.json', metadata)
    for folder in (source, cand):
        np.savez(folder/'bank.npz', position_km=np.ones((1, 3, 3)))
    write(ref/'descriptor.json', dict(files={str(p.relative_to(ref)):'sha256:'+compare.digest(p)
                                           for p in ref.rglob('*') if p.is_file()}))
    native = 'sha256:'+compare.digest(source/'tracking.json')
    write(cand/'summary.json', dict(status='inputs_prepared', position_estimated=False,
                                   input_sha256=native,
                                   source_files={p.name:compare.digest(p) for p in cand.iterdir()}))
    return SimpleNamespace(reference=ref, candidate=cand, reference_noise_source=noise_source,
                           output=tmp_path/'comparison.json')


@pytest.mark.parametrize('mutation', [None, 'coefficient', 'noise', 'element'])
def test_exact_comparator_rejects_scientific_changes_with_valid_new_bindings(tmp_path, mutation):
    args = fixture(tmp_path)
    if mutation:
        name = {'coefficient':'tracks.json', 'noise':'radio_noise.json', 'element':'selected.tle'}[
            mutation]
        path = args.candidate/name
        if mutation == 'element':
            path.write_text('another satellite')
        else:
            value = json.loads(path.read_text())
            if mutation == 'coefficient':
                value['tracks'][0]['coefficients'][0] += 1e-12
            else:
                value['sigma'] += 1e-12
            path.write_text(json.dumps(value))
        summary_path = args.candidate/'summary.json'
        summary = json.loads(summary_path.read_text())
        summary['source_files'][name] = compare.digest(path)
        summary_path.write_text(json.dumps(summary))
    assert compare.run(args) == int(mutation is not None)
    result = json.loads(args.output.read_text())
    assert not result['full_localization_parity']


def test_unbound_artifact_is_rejected(tmp_path):
    args = fixture(tmp_path)
    path = args.candidate/'summary.json'
    value = json.loads(path.read_text())
    del value['source_files']['radio_noise.json']
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='artifact must be bound'):
        compare.run(args)


def test_native_identity_mismatch_rejected(tmp_path):
    args = fixture(tmp_path)
    path = args.candidate/'summary.json'
    value = json.loads(path.read_text())
    value['input_sha256'] = 'sha256:'+hashlib.sha256(b'other input').hexdigest()
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='different native'):
        compare.run(args)


def phase_fixture(tmp_path):
    args = fixture(tmp_path)
    args.with_phase_history = True
    args.reference_history_source = tmp_path/'history.py'
    args.reference_forecast_source = tmp_path/'forecast.py'
    for path in (args.reference_history_source, args.reference_forecast_source):
        path.write_text('source '+path.name)
    history = dict(cutoff_utc_ns=123, past_versions={'1': [dict(epoch=100)]})
    forecast = dict(model=dict(alpha=0.5))
    folder = args.reference/'worker/inference/causal_phase_history'
    folder.mkdir()
    history_path = folder/'SCAN.json'
    history_path.write_text(json.dumps(dict(history,
        source_sha256=compare.digest(args.reference_history_source),
        latest_elements_sha256=compare.digest(
            args.reference/'worker/inference/SCAN/nominal_elements.json'))))
    (folder/'SCAN_forecast.json').write_text(json.dumps(dict(forecast,
        source_sha256=compare.digest(args.reference_forecast_source),
        history_sha256=compare.digest(history_path))))
    (args.candidate/'phase_history.json').write_text(json.dumps(history))
    (args.candidate/'phase_forecast.json').write_text(json.dumps(dict(forecast,
        history_sha256=compare.digest(args.candidate/'phase_history.json'))))
    descriptor_path = args.reference/'descriptor.json'
    descriptor = json.loads(descriptor_path.read_text())
    for path in folder.iterdir():
        descriptor['files'][str(path.relative_to(args.reference))] = 'sha256:'+compare.digest(path)
    descriptor_path.write_text(json.dumps(descriptor))
    rebind_candidate(args)
    return args


def rebind_candidate(args):
    summary_path = args.candidate/'summary.json'
    summary = json.loads(summary_path.read_text())
    for path in args.candidate.iterdir():
        if path != summary_path:
            summary['source_files'][path.name] = compare.digest(path)
    summary_path.write_text(json.dumps(summary))


@pytest.mark.parametrize('mutation', [None, 'history', 'forecast', 'history_binding'])
def test_phase_comparator_rejects_changes(tmp_path, mutation):
    args = phase_fixture(tmp_path)
    if mutation:
        path = args.candidate/('phase_history.json' if mutation == 'history'
                               else 'phase_forecast.json')
        doc = json.loads(path.read_text())
        if mutation == 'history':
            doc['past_versions']['1'][0]['epoch'] += 1
        elif mutation == 'forecast':
            doc['model']['alpha'] += 1e-12
        else:
            doc['history_sha256'] = '0'*64
        path.write_text(json.dumps(doc))
        if mutation == 'history':
            path = args.candidate/'phase_forecast.json'
            doc = json.loads(path.read_text())
            doc['history_sha256'] = compare.digest(args.candidate/'phase_history.json')
            path.write_text(json.dumps(doc))
        rebind_candidate(args)
    if mutation == 'history_binding':
        with pytest.raises(ValueError, match='different history'):
            compare.run(args)
    else:
        assert compare.run(args) == int(mutation is not None)


def test_phase_comparison_requires_original_source_bindings(tmp_path):
    args = fixture(tmp_path)
    args.with_phase_history = True
    with pytest.raises(ValueError, match='both reference source'):
        compare.run(args)


def test_reference_phase_source_cannot_be_replaced(tmp_path):
    args = phase_fixture(tmp_path)
    args.reference_history_source.write_text('different implementation')
    with pytest.raises(ValueError, match='Reference phase provenance'):
        compare.run(args)
