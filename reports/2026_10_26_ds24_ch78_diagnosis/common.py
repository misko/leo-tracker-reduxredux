"""Frozen research imports and output helpers; no geographic reference."""
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import sys

import numpy as np

ROOT = Path(__file__).resolve().parent
REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
SOURCE = Path('/srv/bulk/leo/research/ds25-20261024')
RECOVERY = Path('/srv/bulk/leo/research/ds24-movement-policy-r01/recovery')
OLD = Path('/srv/bulk/leo/research/ds24-receiver-shift-witness-20261025/heldout')
CONTROLS = Path('/srv/bulk/leo/research/ds24-receiver-orbit-controls-20261025')
sys.path[:0] = ['/tmp/algo03-feasible-deps',str(REPO/'src'),str(REPO/'tools'),str(RECOVERY),
    str(CONTROLS/'evaluation'),str(CONTROLS/'receiver')]
import recovery as r
from investigate_dsx01_localization_failures import fit
from probe_ds23_graph_seeded_paths import build

CASES = ('DS24-0010','DS24-0011','DS24-0012','DS24-0013')
ARMS = ('c0','fitted_c')


def module(name, path):
    spec=importlib.util.spec_from_file_location(name,path)
    value=importlib.util.module_from_spec(spec);spec.loader.exec_module(value)
    return value


h = module('prior_whole_family_prediction', OLD/'heldout.py')
frozen = module('full_precision_model', Path('/srv/bulk/leo/research/ds24-cfo-precision-factorial-r01/solver/model.py'))


def load(path): return json.loads(Path(path).read_text())
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def encode(value):
    if isinstance(value,np.ndarray):return value.tolist()
    if isinstance(value,np.generic):return value.item()
    if isinstance(value,Path):return str(value)
    raise TypeError(type(value).__name__)
def write(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('x') as stream:
        json.dump(value,stream,indent=2,default=encode,allow_nan=False);stream.write('\n')


def cap(seconds):
    signal.signal(signal.SIGALRM,lambda *_:(_ for _ in ()).throw(TimeoutError('frozen numerical worker budget')))
    signal.setitimer(signal.ITIMER_REAL,seconds)


def context(case):
    d=r.context(case)
    for arm in ARMS:
        saved=d['arms'][arm];p=build(d,'default',arm,saved['phase_reference'])
        delta=p.calculate(saved['endpoint_east_north_km'])['negative_twice_elbo']-saved['negative_twice_elbo']
        assert abs(delta)<1e-3
    return d


def metadata(p):
    ids=[];channels=[];receivers=[];families=[]
    for row,i,sl in zip(p.rows,p.members,p.slices,strict=True):
        t=p.scan.tracks[i];n=sl.stop-sl.start
        ids.extend(t['observation_ids']);channels.extend([t['channel']]*n)
        receivers.extend([t['receiver']]*n);families.extend([row['candidate_index']]*n)
    assert len(ids)==len(set(ids))
    return dict(ids=np.array(ids),channel=np.array(channels),receiver=np.array(receivers),
                family=np.array(families),time=p.flat_times)


def source_manifest():
    sources={str(Path(__file__)):sha(__file__),str(ROOT/'PROTOCOL.md'):sha(ROOT/'PROTOCOL.md')}
    for mod in list(sys.modules.values()):
        filename=getattr(mod,'__file__',None)
        if filename and Path(filename).suffix=='.py' and (Path(filename).is_relative_to(REPO) or
            Path(filename).is_relative_to('/srv/bulk/leo/research')):
            sources[str(Path(filename))]=sha(filename)
    for case in CASES:
        for path in [SOURCE/'family_cavity/position'/(case+'.json'),
            *[SOURCE/case/n for n in ('tracks.json','observations.json','bank.npz','nominal_elements.json','receipt.json','radio_noise.json')]]:
            if path.exists():sources[str(path)]=sha(path)
    return sources


def verify(mapping):
    for path,digest in mapping.items():
        assert sha(path)==digest, 'frozen file changed: '+path
