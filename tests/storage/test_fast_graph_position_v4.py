import json
import pytest
from leo.storage.fast_graph_position import sha
from leo.storage.fast_graph_position_v3_export import FastGraphPositionStoreV3Export
from leo.storage.graph_position_view_v4 import GraphPositionViewV4
from leo.contracts.fast_graph_position_v4 import MODEL_VERSION

def test_private_export_copies_bytes_and_rejects_links(tmp_path,monkeypatch):
    (tmp_path/'bulk').mkdir()
    store=FastGraphPositionStoreV3Export(tmp_path/'bulk');root=store.path('job')/'output';source=root/'recovery/data.json'
    source.parent.mkdir(parents=True);source.write_text('{"source":1}');terminal=root/'terminal.json';terminal.write_text('{}')
    job=dict(job_id='job',input_sha256='sha256:test')
    monkeypatch.setattr(store,'status',lambda _:dict(state='complete'))
    monkeypatch.setattr(store,'terminal',lambda _:(dict(state='complete',session_id='scan'),dict(path=str(terminal),sha256=sha(terminal))))
    dest=tmp_path/'export';d=store.export_recovery(job,dest)
    assert d['model_version']=='algo04-causal-numerical-v1'
    assert (dest/'recovery/data.json').read_bytes()==source.read_bytes()
    (dest/'recovery/data.json').write_text('changed');assert json.loads(source.read_text())=={'source':1}
    (source.parent/'escape').symlink_to(tmp_path/'missing')
    with pytest.raises(ValueError,match='symbolic'):store.export_recovery(job,tmp_path/'bad')

def test_missing_gap_result_keeps_actual_previous_position():
    class Previous:
        def detail(self,_):return dict(position={'latitude_deg':37.,'longitude_deg':-122.},selected_model='algo04-causal-numerical-v1',reason=None,decision='ALGO04_additive')
    class Empty:
        def inputs(self,**_):return []
    d=GraphPositionViewV4('.',MODEL_VERSION,previous=Previous(),recovery=Empty()).detail('scan')
    assert d['position']=={'latitude_deg':37.,'longitude_deg':-122.}
    assert d['selected_model']==MODEL_VERSION and d['fallback']
