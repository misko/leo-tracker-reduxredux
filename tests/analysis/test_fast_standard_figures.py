from io import BytesIO
from PIL import Image
from leo.presentation.fast_standard_analysis import render
from leo.contracts.fast_standard_analysis import PLOTS
from leo.presentation.orbit_plot import OrbitLane, OrbitPeak, OrbitCurve


def test_all_eight_figures_render_the_same_native_memberships():
    observations=[dict(observation_id='one',receiver=1,channel=1,time_s=1.,measured_cfo_hz=100.),
                  dict(observation_id='two',receiver=1,channel=1,time_s=2.,measured_cfo_hz=110.)]
    row=dict(observations[0],norad=123,residual_hz=2.,prediction_hz=98.,component='track')
    lanes=tuple(OrbitLane(f'RX{rx}',f'CH{ch}',
        (OrbitPeak('one',1.,98.,'123'),OrbitPeak('two',2.,108.)) if (rx,ch)==(1,1) else (),
        (OrbitCurve('123',(0.,300.),(98.,-98.)),)) for ch in range(1,9) for rx in (1,2))
    packet=dict(observations=observations,tracks=[],rows=dict(fitted_c=[row]),orbit_lanes=lanes,
                arms={a:dict(endpoint_latlon=[37.9,-122.5]) for a in ('c0','fitted_c')})
    pngs=render(packet,title='Synthetic membership verification')
    assert set(pngs)==set(PLOTS)
    for data in pngs.values():
        with Image.open(BytesIO(data)) as image:
            image.verify()
    assert packet['observations']==observations and packet['rows']['fitted_c']==[row]


def test_standard_main_pngs_use_the_existing_orbit_renderer(monkeypatch):
    from leo.presentation import fast_standard_analysis as figures
    from leo.presentation.fast_scan_orbits import render_fast_scan_orbits
    calls=[]
    def capture(lanes,**kwargs):
        calls.append((lanes,kwargs))
        return render_fast_scan_orbits(lanes,**kwargs)
    monkeypatch.setattr(figures,'render_fast_scan_orbits',capture)
    test_all_eight_figures_render_the_same_native_memberships()
    lanes,options=calls[0]
    assert [(x.channel,x.receiver) for x in lanes]==[(f'CH{ch}',f'RX{rx}') for ch in range(1,9) for rx in (1,2)]
    assert options['alias_period_hz']==1/4.4e-6
    assert 'receiver calibration removed' in options['subtitle']
