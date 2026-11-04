import importlib.util
from pathlib import Path

import pytest

from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
from tests.storage.test_fast_standard_analysis import publication


@pytest.fixture
def renderer():
    path = Path(__file__).resolve().parents[2] / 'tools/render_standard_fast.py'
    spec = importlib.util.spec_from_file_location('standard_renderer_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reference_validation(renderer):
    assert renderer.evaluation_coordinates(None, None) is None
    for lat, lon in [(None, 0), (0, None), (float('nan'), 0), (91, 0), (0, 181)]:
        with pytest.raises(ValueError):
            renderer.evaluation_coordinates(lat, lon)


@pytest.mark.parametrize('existing', [False, True])
def test_evaluation_passed_only_to_presentation_and_saved_after_completion(
        tmp_path, monkeypatch, renderer, existing):
    store = FastStandardAnalysisStore(tmp_path)
    document, pngs = publication()
    site = dict(latitude_deg=37.849061591561885, longitude_deg=-122.48574968092912)
    saved = dict(latitude_deg=38., longitude_deg=-123.)
    if existing:
        store.publish('run', document, pngs)
        store.set_evaluation_reference('run', **saved)
    calls = []

    def render(source, target, job, *, evaluation_reference):
        calls.append(evaluation_reference)
        if not existing:
            assert target.detail('run')['state'] == 'pending'
        return target.publish('run', document, pngs)

    monkeypatch.setattr(renderer, '_publish', render)
    renderer.publish(object(), store, dict(run_id='run'), evaluation_reference=site)
    expected = saved if existing else site
    assert len(calls) == 1
    assert {k: calls[0][k] for k in expected} == expected
    result = store.detail('run')
    assert result['evaluation_reference']['latitude_deg'] == calls[0]['latitude_deg']
    assert result['arms']['fitted_c']['evaluation_error_m'] > 0
