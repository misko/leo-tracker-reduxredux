from fastapi import FastAPI
from fastapi.testclient import TestClient
from leo.api.fast_standard_analysis import standard_analysis_router


def test_digest_bound_artifact_and_pending_routes():
    class Reader:
        def detail(self,run_id):return dict(run_id=run_id,state='pending')
        def position_grid(self,run_id):return dict(kind='conditional-position-grid') if run_id=='scan' else None
        def position_path(self,run_id):return dict(kind='recorded-position-path') if run_id=='scan' else None
        def artifact(self,run_id,name,expected):
            if run_id!='scan' or name!='position' or expected!='sha256:correct':raise ValueError('stale')
            return b'PNG'
    app=FastAPI();app.include_router(standard_analysis_router(Reader()));client=TestClient(app)
    assert client.get('/api/v2/fast-scans/scan/standard-analysis').json()['state']=='pending'
    response=client.get('/api/v2/fast-scans/scan/standard-analysis/position.png?sha256=sha256:correct')
    assert response.status_code==200 and response.headers['content-type']=='image/png'
    assert 'immutable' in response.headers['cache-control']
    assert client.get('/api/v2/fast-scans/scan/standard-analysis/position.png?sha256=stale').status_code==404
    grid=client.get('/api/v2/fast-scans/scan/standard-analysis/position-grid.json')
    assert grid.status_code==200 and grid.json()['kind']=='conditional-position-grid'
    assert client.get('/api/v2/fast-scans/missing/standard-analysis/position-grid.json').status_code==404
    path=client.get('/api/v2/fast-scans/scan/standard-analysis/position-path.json')
    assert path.status_code==200 and path.json()['kind']=='recorded-position-path'
    assert client.get('/api/v2/fast-scans/missing/standard-analysis/position-path.json').status_code==404


def test_comparison_requires_one_acquisition_and_both_models():
    from leo.contracts.fast_standard_analysis import ALGO08, ALGO08V2, ALGO08V3, MODEL, PLOTS
    class Reader:
        def detail(self, rid):
            return dict(run_id=rid, state='complete',
                        model_version={'new':ALGO08,'v2':ALGO08V2,'v3':ALGO08V3}.get(rid, MODEL),
                        session_id='other' if rid=='wrong' else 's',
                        artifacts=[dict(name=name, sha256='sha256:abc') for name in PLOTS])
    app=FastAPI()
    app.include_router(standard_analysis_router(Reader()))
    client=TestClient(app)
    base='/api/v2/fast-scans/new/standard-analysis/compare/'
    gallery=client.get(base+'old')
    assert gallery.status_code==200 and gallery.text.count('<img ')==16
    assert gallery.text.index('ALGO07 position') < gallery.text.index('ALGO08 position')
    v2=client.get('/api/v2/fast-scans/old/standard-analysis/compare/v2')
    assert v2.status_code==200 and v2.text.count('ALGO08v2 position')==1
    v3=client.get('/api/v2/fast-scans/old/standard-analysis/compare/v3')
    assert v3.status_code==200 and v3.text.count('ALGO08v3 position')==1
    assert client.get(base+'wrong').status_code==404
    assert client.get(base+'new').status_code==404


def test_v3_pending_and_withheld_routes_preserve_model_and_release(tmp_path):
    from leo.contracts.algo08v3 import EXECUTION_RELEASE
    from leo.contracts.fast_standard_analysis import ALGO08V3
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    store = FastStandardAnalysisStore(tmp_path)
    app = FastAPI()
    app.include_router(standard_analysis_router(store))
    client = TestClient(app)
    run_id = "algo08-v3-" + "a" * 32
    base = f"/api/v2/fast-scans/{run_id}/standard-analysis"
    pending = client.get(base)
    assert pending.status_code == 200
    assert pending.json()["model_version"] == ALGO08V3
    assert pending.json()["schema_version"] == 3
    assert pending.json()["state"] == "pending"

    region = dict(center=[37.85, -122.48], screen_center=[37.85, -122.48], width_km=18.)
    withheld = store.withhold(run_id, "no_active_curvature", region=region,
                             execution_release=EXECUTION_RELEASE)
    assert client.get(base).json() == withheld
    assert client.get(base + "/position.png").status_code == 404
