import copy
from io import BytesIO
import pytest
from PIL import Image
from leo.contracts.fast_standard_analysis import PLOTS,MODEL,validate
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore


def publication():
    s=BytesIO();Image.new('RGB',(2,2)).save(s,format='PNG')
    pngs=dict.fromkeys(PLOTS,s.getvalue())
    arm=dict(endpoint_latlon=[37.842403850242285,-122.49124137019581],associated_points=1)
    doc=dict(schema_version=1,run_id='run',state='complete',model_version=MODEL,
             reference_usage='evaluation_only',glrt_points=2,arms=dict(c0=arm,fitted_c=arm))
    return doc,pngs


def test_eight_figures_publish_atomically_and_reference_is_postfit_only(tmp_path):
    store=FastStandardAnalysisStore(tmp_path);d,pngs=publication()
    assert store.detail('run')['state']=='pending'
    with pytest.raises(ValueError,match='All standard figures'):store.publish('run',d,{})
    result=store.publish('run',d,pngs)
    assert len(result['artifacts'])==8
    before=(store.folder('run')/'manifest.json').read_bytes()
    store.set_evaluation_reference('run',37.849061591561885,-122.48574968092912)
    assert (store.folder('run')/'manifest.json').read_bytes()==before
    assert store.detail('run')['arms']['fitted_c']['evaluation_error_m']==pytest.approx(883.504916204,abs=1e-6)
    for a in result['artifacts']:
        assert store.artifact('run',a['name'],a['sha256'])==pngs[a['name']]
        with pytest.raises(FileNotFoundError):store.artifact('run',a['name'],'sha256:stale')


def test_corrupt_or_cross_scan_figures_fail_closed(tmp_path):
    store=FastStandardAnalysisStore(tmp_path);d,pngs=publication()
    with pytest.raises(ValueError,match='another scan'):store.publish('other',d,pngs)
    result=store.publish('run',d,pngs);a=result['artifacts'][0]
    (store.folder('run')/(a['sha256'].split(':')[1]+'.png')).write_bytes(b'corrupt')
    with pytest.raises(ValueError,match='integrity'):store.artifact('run',a['name'])
    d=store.detail('run');d['artifacts'][0]['sha256']='../../escape'
    with pytest.raises(ValueError,match='digest'):validate(d)


def test_publication_preserves_existing_revision(tmp_path):
    store=FastStandardAnalysisStore(tmp_path);d,pngs=publication();store.publish('run',d,pngs)
    changed=copy.deepcopy(d);changed['arms']['c0']['associated_points']=0
    with pytest.raises(ValueError,match='immutable'):store.publish('run',changed,pngs)


def test_layout_revision_preserves_old_digest_urls_and_evaluation_reference(tmp_path):
    import json
    from leo.storage.fast_standard_analysis import digest
    store=FastStandardAnalysisStore(tmp_path);d,pngs=publication()
    old=store.publish('run',d,pngs)
    store.set_evaluation_reference('run',37.849061591561885,-122.48574968092912)
    base=store.base_folder('run')
    for path in store.folder('run').iterdir():
        path.rename(base/path.name)
    new_pngs={name:data+b'render revision' for name,data in pngs.items()}
    new=store.publish('run',d,new_pngs)
    assert json.loads((base/'manifest.json').read_text())==old
    assert store.detail('run')['arms']['fitted_c']['evaluation_error_m']==pytest.approx(883.504916204,abs=1e-6)
    for a in old['artifacts']:
        assert store.artifact('run',a['name'],a['sha256'])==pngs[a['name']]
    for a in new['artifacts']:
        assert store.artifact('run',a['name'])==new_pngs[a['name']]
        assert a['sha256']==digest(new_pngs[a['name']])


def test_previous_layout_remains_available_during_atomic_upgrade(tmp_path):
    import json
    from leo.storage.fast_standard_analysis import PREVIOUS_RENDER_REVISIONS
    store=FastStandardAnalysisStore(tmp_path);d,pngs=publication()
    d['renderer_revision']=PREVIOUS_RENDER_REVISIONS[0]
    old=store.publish('run',d,pngs)
    store.set_evaluation_reference('run',37.849061591561885,-122.48574968092912)
    old_folder=store.base_folder('run')/PREVIOUS_RENDER_REVISIONS[0]
    store.folder('run').rename(old_folder)
    assert store.detail('run')['state']=='complete'
    assert store.detail('run')['renderer_revision']==PREVIOUS_RENDER_REVISIONS[0]
    assert store.artifact('run','position')==pngs['position']
    changed=dict(pngs,position=pngs['position']+b'new map')
    store.publish('run',dict(d,renderer_revision='new'),changed)
    assert store.artifact('run','position')==changed['position']
    for a in old['artifacts']:
        assert store.artifact('run',a['name'],a['sha256'])==pngs[a['name']]
    assert json.loads((old_folder/'manifest.json').read_text())==old
    assert store.detail('run')['evaluation_reference']['latitude_deg']==37.849061591561885


def test_previous_reader_can_observe_completion_without_seeing_new_layout(tmp_path):
    from leo.storage.fast_standard_analysis import PREVIOUS_RENDER_REVISIONS
    current=FastStandardAnalysisStore(tmp_path)
    previous=FastStandardAnalysisStore(tmp_path,revision=PREVIOUS_RENDER_REVISIONS[0])
    d,pngs=publication()
    current.publish('run',d,pngs)
    assert previous.detail('run')['state']=='pending'
    previous.publish('run',d,pngs)
    assert previous.detail('run')['state']=='complete'
    assert previous.artifact('run','position')==pngs['position']
