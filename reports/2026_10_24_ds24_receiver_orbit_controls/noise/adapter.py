"""In-memory receiver-specific noise adapter; original contracts stay immutable."""
from pathlib import Path
import copy, hashlib, json
import numpy as np
from probe_ds23_graph_seeded_paths import build as original_build
from ds23_predictive_linear import linear_geometry

HERE=Path(__file__).resolve().parent

def build(d,arm,reference,case):
    source=HERE/'results'/f'{case}.json';saved=json.loads(source.read_text())
    if not saved['qualified']:raise ValueError('receiver noise law failed frozen grouped prediction')
    scan=copy.copy(d['scan']);noise=saved['per_observation_noise_sigma_hz']
    scan.fixed_window_noise=dict(scan.fixed_window_noise,
        per_observation_noise_sigma_hz=noise,extra_parameter_BIC_gain=1.0,
        experimental_selector_flag_not_measured_BIC=True)
    scan.fixed_window_noise_sha256=hashlib.sha256(source.read_bytes()).hexdigest()
    p=original_build(dict(d,scan=scan),'default',arm,reference)
    ids=[oid for i in p.members for oid in scan.tracks[i]['observation_ids']]
    np.testing.assert_allclose(p.point_noise,[noise[o] for o in ids],atol=0,rtol=0)
    if d['entries']:
        _,_,sigma,_,_=linear_geometry(p,d['entries'])
        ids=[oid for e in d['entries'] for oid in scan.tracks[e['track_index']]['observation_ids']]
        np.testing.assert_allclose(sigma,[noise[o] for o in ids],atol=0,rtol=0)
    return p
