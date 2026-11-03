from fastapi import FastAPI
from fastapi.testclient import TestClient
from leo.api.fast_standard_analysis import standard_analysis_router


def test_digest_bound_artifact_and_pending_routes():
    class Reader:
        def detail(self,run_id):return dict(run_id=run_id,state='pending')
        def position_grid(self,run_id):return dict(kind='conditional-position-grid') if run_id=='scan' else None
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
