from io import BytesIO
from PIL import Image
from leo.presentation.fast_standard_analysis import render
from leo.contracts.fast_standard_analysis import PLOTS


def test_all_eight_figures_render_the_same_native_memberships():
    observations=[dict(observation_id='one',receiver=1,channel=1,time_s=1.,measured_cfo_hz=100.),
                  dict(observation_id='two',receiver=1,channel=1,time_s=2.,measured_cfo_hz=110.)]
    row=dict(observations[0],norad=123,residual_hz=2.,prediction_hz=98.,component='track')
    packet=dict(observations=observations,tracks=[],rows=dict(fitted_c=[row]),
                arms={a:dict(endpoint_latlon=[37.9,-122.5]) for a in ('c0','fitted_c')})
    pngs=render(packet,title='Synthetic membership verification')
    assert set(pngs)==set(PLOTS)
    for data in pngs.values():
        with Image.open(BytesIO(data)) as image:
            image.verify()
    assert packet['observations']==observations and packet['rows']['fitted_c']==[row]
