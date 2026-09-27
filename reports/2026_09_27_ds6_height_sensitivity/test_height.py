import numpy as np
from run_height import HeightObjective,elevated_site
from run_baseline import Objective,site,REFERENCE_RF_HZ,LIGHT_KM_S
from leo.sky.frames import geodetic_to_ecef_km


def test_elevated_site_matches_geodetic_conversion():
    for lat,lon in [(37.8,-122.4),(-20.,40.),(80.,-5.)]:
        for height in [0.,100.,1000.]:
            # Public frame function accepts metres and returns kilometres.
            expected=geodetic_to_ecef_km(lat,lon,height)
            actual,_=elevated_site(lat,lon,height)
            np.testing.assert_allclose(actual,expected,rtol=0,atol=1e-9)


def synthetic_base():
    center=[37.8,-122.4];rec,up=site(*center);east=np.array([-up[1],up[0],0.]);east/=np.linalg.norm(east)
    t=np.linspace(0.,300.,101);pos=rec+600*up+(t-150.)[:,None]*east*2.;vel=np.broadcast_to(7.5*east,pos.shape).copy()
    unit=pos-rec;unit/=np.linalg.norm(unit,axis=-1)[:,None]
    y=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(unit*vel,axis=-1)+10000.
    mask=np.isin(np.minimum((t/30).astype(int),9),[0,2,3,6,7,9])
    track=dict(track_id='one',receiver_id=0,t=t,y=y,mask=mask,centered_t=t-t[mask].mean())
    bank=(np.broadcast_to(pos,(1,41,len(t),3)).copy(),np.broadcast_to(vel,(1,41,len(t),3)).copy(),np.array([0]))
    return Objective([track],{'one':bank},center,1,[0])


def test_zero_height_reproduces_model_and_held_values_do_not_affect_training():
    base=synthetic_base();model=HeightObjective(base,0.);x=np.array([.2,-.3,.1])
    before=model.evaluate(x);old=base.evaluate(x,False)
    for key in ['train','held']:np.testing.assert_allclose(before[key],old[key],atol=1e-9)
    elevated=HeightObjective(base,250.);train=elevated.evaluate(x)['train']
    t=base.tracks[0];t['y']=t['y']+np.where(t['mask'],0.,1e6)
    assert elevated.evaluate(x)['train']==train


def test_injected_height_is_selected_at_fixed_horizontal_position():
    base=synthetic_base();t=base.tracks[0];p,v,_=base.banks[t['track_id']]
    rec=geodetic_to_ecef_km(*base.center,250.)
    unit=p[0,0]-rec;unit/=np.linalg.norm(unit,axis=-1)[:,None]
    t['y']=-REFERENCE_RF_HZ/LIGHT_KM_S*np.sum(unit*v[0,0],axis=-1)+10000.
    scores={h:HeightObjective(base,h).evaluate(np.zeros(3))['train'] for h in [0.,100.,250.,500.,1000.]}
    assert max(scores,key=scores.get)==250.


def test_frozen_real_height_profiles():
    import json
    from run_height import HERE,REPORTS,digest
    protocol=json.loads((HERE/'protocol.json').read_text())
    assert protocol['source_sha256']==digest(HERE/'run_height.py')
    assert protocol['frame_source_sha256']==digest(REPORTS.parent/'src/leo/sky/frames.py')
    for name,value in protocol['files'].items():assert digest(REPORTS/name)==value
    for session in protocol['sessions']:
        result=json.loads((HERE/f'{session}.json').read_text())
        assert result['complete'] and result['protocol_sha256']==digest(HERE/'protocol.json')
        assert [a['height_m'] for a in result['arms']]==protocol['heights_m']
        assert result['selected_height_m']==max(result['arms'],key=lambda a:a['best']['train'])['height_m']
        for arm in result['arms']:
            assert arm['best']==max(arm['runs'],key=lambda r:r['train'])
            assert len(arm['runs'])==3
            assert arm['maximum_interpolation_error_hz']<.05
            assert abs(arm['best']['train']-arm['exact_train'])<1.
