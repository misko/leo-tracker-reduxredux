from types import SimpleNamespace
from catalogue import choose_records


def test_element_epoch_beats_download_time_and_preserves_rows():
    a=SimpleNamespace(satellite_number=10,text='old')
    b=SimpleNamespace(satellite_number=10,text='new')
    c=SimpleNamespace(satellite_number=20,text='other')
    chosen=choose_records([c,a],[(200,'mirror',[a,c],[100,105]),(150,'primary',[b],[120])])
    assert [r.text for _,r in chosen]==['other','new']
    assert chosen[1][0]==(120,150,'primary')


def test_equal_epochs_choose_latest_collection_deterministically():
    a=SimpleNamespace(satellite_number=10,text='a')
    b=SimpleNamespace(satellite_number=10,text='b')
    sources=[(200,'z',[a],[100]),(201,'a',[b],[100])]
    assert choose_records([a],sources)==choose_records([a],list(reversed(sources)))
    assert choose_records([a],sources)[0][1].text=='b'


def test_latest_provider_selection_strictly_excludes_cutoff_and_future(monkeypatch):
    import catalogue
    records={k:SimpleNamespace(satellite_number=10,text=k) for k in ['old','new','future']}
    snapshots=[SimpleNamespace(provider=p,collected_utc_ns=t,digest=k,sha256=k) for p,t,k in
        [('primary',90,'new'),('mirror',110,'old'),('primary',120,'future'),('mirror',130,'future')]]
    class Archive:
        def list_snapshots(self):return snapshots
        def select_latest_before(self,cutoff):return max((s for s in snapshots if s.collected_utc_ns<cutoff),key=lambda s:s.collected_utc_ns)
    cache={k:([r],SimpleNamespace(satellite_numbers=(10,)),(e,)) for (k,r),e in zip(records.items(),[100,200,300])}
    monkeypatch.setattr(catalogue,'parse_element_sets',lambda text:SimpleNamespace(satellite_numbers=(10,)))
    _,_,provenance=catalogue.catalogues(Archive(),505_000_000_120,'old',cache)
    assert [s['digest'] for s in provenance['providers']]==['old','new']
    assert provenance['element_source'][0]['snapshot_digest']=='new'
    assert provenance['changed_rows']==[0]


def test_all43_audit_is_source_bound_and_keeps_causal_inputs():
    import json,hashlib
    from catalogue import HERE,REPORTS
    def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    audit=json.loads((HERE/'audit.json').read_text())
    assert audit['source_sha256']==digest(HERE/'audit.py')
    assert audit['catalogue_source_sha256']==digest(HERE/'catalogue.py')
    for name,value in audit['inputs'].items():assert digest(REPORTS/name)==value
    assert len({r['session_id'] for r in audit['results']})==43
    for row in audit['results']:
        data=json.loads((REPORTS/'2026_09_27_ds6_cfo_dataset'/f"{row['session_id']}-plan.json").read_text())
        assert all(p['collected_utc_ns']<data['start_utc_ns']-505_000_000_000 for p in row['providers'])
        assert row['baseline_digest']==data['snapshot_digest']
        assert all(t['new_age_h']<=t['old_age_h'] for t in row['tracks'])


def test_all43_fits_and_exact_baseline_reuse():
    import json,hashlib
    from catalogue import HERE,REPORTS
    def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert protocol['source_sha256']==digest(HERE/'run_fresh.py')
    for name,value in protocol['files'].items():assert digest(REPORTS/name)==value
    assert len(set(protocol['sessions']))==43
    refitted=reused=0
    for session in protocol['sessions']:
        result=json.loads((HERE/f'{session}.json').read_text())
        assert result['complete'] and result['state']=='complete'
        assert result['protocol_sha256']==digest(HERE/'protocol.json')
        assert result['best']==max(result['runs'],key=lambda r:r['train'])
        assert result['maximum_interpolation_error_hz']<.05
        if result['inference_reused']:
            reused+=1
            baseline_path=REPORTS/'2026_09_27_ds6_full_cfo'/f'{session}.json'
            baseline=json.loads(baseline_path.read_text())
            assert result['reused_baseline_sha256']==digest(baseline_path)
            assert result['element_provenance']['changed_rows']==[]
            for key in ['best','runs','shortlists','exact_train','exact_held']:
                assert result[key]==baseline[key]
        else:
            refitted+=1
            assert result['element_provenance']['changed_rows']
            assert len(result['runs'])==3
    assert (refitted,reused)==(5,38)
