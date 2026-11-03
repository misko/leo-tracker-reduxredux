import hashlib
import json
from pathlib import Path
import numpy as np
from leo.contracts.regional_position import PositionObservations,PositionOrbitBank,RegionalPrior,PositionScore
HERE=Path(__file__).resolve().parent
def digest(path):return 'sha256:'+hashlib.sha256(Path(path).read_bytes()).hexdigest()
def load(label):
    folder=HERE/'inputs'/label
    d=json.loads((folder/'inputs.json').read_text())
    assert digest(folder/'arrays.npz')==d['arrays_sha256']
    with np.load(folder/'arrays.npz',allow_pickle=False) as a:
        obs=PositionObservations(tuple(a['obs_window_ids'].tolist()),**{n:a['obs_'+n] for n in
            ('times_s','measured_hz','rf_hz','receiver','channel','margin')})
        bank=PositionOrbitBank(**{n:a['bank_'+n] for n in ('numbers','nodes_s','position_km','velocity_km_s')})
    return d,obs,bank,RegionalPrior(**d['prior']),PositionScore(**d['score'])
