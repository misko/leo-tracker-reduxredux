"""The map upgrade must not change any saved scientific result or orbit PNG."""
import copy
from io import BytesIO

from PIL import Image

from leo.contracts.fast_standard_analysis import PLOTS, MODEL
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore, PREVIOUS_RENDER_REVISIONS
import render_standard_fast as worker


def test_upgrade_reuses_saved_pngs_without_scientific_replay(tmp_path,monkeypatch):
    target=FastStandardAnalysisStore(tmp_path)
    image=BytesIO();Image.new('RGB',(2,2)).save(image,format='PNG')
    pngs=dict.fromkeys(PLOTS,image.getvalue())
    arm=dict(endpoint_latlon=[37.85,-122.48],associated_points=1,
             owner_sha256='sha256:owners',residual_rms_hz=100.)
    document=dict(schema_version=1,run_id='run',state='complete',model_version=MODEL,
        selected_model='algo02-causal-family-v1',reference_usage='evaluation_only',
        glrt_points=2,arms=dict(c0=copy.deepcopy(arm),fitted_c=copy.deepcopy(arm)),
        objective_replay=dict(c0=0.,fitted_c=0.),terminal_sha256='sha256:terminal',
        renderer_revision=PREVIOUS_RENDER_REVISIONS[0])
    target.publish('run',document,pngs)
    target.set_evaluation_reference('run',37.849061591561885,-122.48574968092912)
    target.folder('run').rename(target.base_folder('run')/PREVIOUS_RENDER_REVISIONS[0])
    terminal=dict(sealed=True)
    class Source:
        def terminal(self,job):return terminal,dict(sha256='sha256:terminal')
        def plot_evidence(self,job):raise AssertionError('No scientific replay for a map-only upgrade')
    monkeypatch.setattr(worker,'completed_view',lambda run,value:
        dict(selected=dict(arms=document['arms'])))
    result=worker.publish(Source(),target,dict(run_id='run',job_id='job'))
    for key in ('arms','objective_replay','terminal_sha256','glrt_points','selected_model'):
        assert result[key]==document[key]
    for name in PLOTS:
        data=target.artifact('run',name)
        if name=='position':
            assert data!=pngs[name]
            with Image.open(BytesIO(data)) as image:assert image.size==(1080,960)
        else:assert data==pngs[name]


def test_fresh_publication_remains_visible_to_live_previous_revision_watcher(tmp_path,monkeypatch):
    target=FastStandardAnalysisStore(tmp_path)
    image=BytesIO();Image.new('RGB',(2,2)).save(image,format='PNG')
    pngs=dict.fromkeys(PLOTS,image.getvalue())
    arm=dict(endpoint_latlon=[37.85,-122.48],associated_points=1)
    evidence=dict(terminal=dict(session_id='session',decision='ALGO06_fallback'),
        terminal_receipt=dict(sha256='sha256:terminal'),observation_sha256='sha256:observations',
        tracks_sha256='sha256:tracks')
    class Source:
        def plot_evidence(self,job):return evidence
    monkeypatch.setattr(worker,'replay',lambda *_:dict(arms=dict(c0=arm,fitted_c=arm),
        selected_model='algo02-causal-family-v1',observations=[dict()],
        objective_replay=dict(c0=0.,fitted_c=0.)))
    monkeypatch.setattr(worker,'render',lambda *args,**kwargs:pngs)
    worker.publish(Source(),target,dict(run_id='run',job_id='job',input_sha256='sha256:input'))
    previous=FastStandardAnalysisStore(tmp_path,revision=PREVIOUS_RENDER_REVISIONS[0])
    assert previous.detail('run')['state']=='complete'
    assert previous.detail('run')['terminal_sha256']==target.detail('run')['terminal_sha256']
    assert target.detail('run')['state']=='complete'
    for name in PLOTS:assert previous.artifact('run',name)==target.artifact('run',name)
