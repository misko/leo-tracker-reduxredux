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


def test_position_map_restores_reference_marker_and_reports_actual_error():
    import copy
    from leo.presentation.fast_standard_analysis import position_figure
    arms={'c0':dict(endpoint_latlon=[37.85041788079218,-122.47576435392004],residual_rms_hz=105.94),
          'fitted_c':dict(endpoint_latlon=[37.85027474651324,-122.47676566198743],residual_rms_hz=107.64)}
    before=copy.deepcopy(arms)
    reference=dict(latitude_deg=37.849061591561885,longitude_deg=-122.48574968092912)
    figure=position_figure(arms,title='Saved scan',selected_model='algo02-causal-family-v1',
                           evaluation_reference=reference)
    axis=figure.axes[0]
    markers={line.get_label():line for line in axis.lines}
    gps=markers['Reference (evaluation only)']
    assert gps.get_marker()=='+'
    # The evaluation site is offset from the regional centre; it is not (0, 0).
    assert 5 < gps.get_xdata()[0] < 5.5 and -6.5 < gps.get_ydata()[0] < -6
    assert markers['Fitted c selected estimate'].get_marker()=='D'
    assert markers['c = 0 selected estimate'].get_marker()=='s'
    assert 'reference error 800.3 m' in axis.get_title()
    assert 'reference error 889.6 m' in axis.get_title()
    assert 'retained ALGO02' in figure._suptitle.get_text()
    assert arms==before


def test_position_without_evaluation_reference_does_not_invent_ground_truth():
    from leo.presentation.fast_standard_analysis import position_figure
    arms={a:dict(endpoint_latlon=[37.9,-122.5]) for a in ('c0','fitted_c')}
    figure=position_figure(arms,title='Unreferenced scan')
    axis=figure.axes[0]
    assert all(line.get_label()!='Reference (evaluation only)' for line in axis.lines)
    assert axis.get_title().count('evaluation reference unavailable')==2


def test_algo07_grid_reuses_historical_colored_grid_renderer(monkeypatch):
    from leo.presentation import fast_standard_analysis as figures
    from leo.presentation.regional_position import draw_position_grid
    calls=[]
    def capture(figure,axis,points,**kwargs):
        points=list(points);calls.append(points)
        return draw_position_grid(figure,axis,points,**kwargs)
    monkeypatch.setattr(figures,'draw_position_grid',capture)
    arms={a:dict(endpoint_latlon=[37.9,-122.5]) for a in ('c0','fitted_c')}
    grid=dict(points=[dict(east_km=0.,north_km=0.,latlon=[37.906,-122.545],scores=dict(c0=11.,fitted_c=10.)),
                      dict(east_km=4.,north_km=-1.,latlon=[37.9,-122.5],scores=dict(c0=12.,fitted_c=14.))],
              evaluated_points=2,planned_points=2,complete=True)
    figure=figures.position_figure(arms,title='Grid',position_grid=grid)
    assert len(calls)==1 and [p[2] for p in calls[0]]==[10.,14.]
    assert len(figure.axes)==2
    assert 'Conditional fitted-c objective' in figure.axes[1].get_ylabel()
    assert 'fixed satellite associations' in figure._supxlabel.get_text()
