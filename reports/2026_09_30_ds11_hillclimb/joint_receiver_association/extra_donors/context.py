"""Read hash-bound numerical exports at frozen N23 station geometry."""
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'tools'))
import ds7_fast_baseline_adapter as fast
def read(p):return json.loads(Path(p).read_text())
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(index):
    proof=HERE/'numeric-summary.json';verified=read(proof);assert verified['passed']
    for p,h in verified['sources'].items():assert digest(p)==h,p
    geometry_path=HERE.parent/'causal-calibration-geometry.polished.json';geometry=read(geometry_path)
    assert geometry['fit']['qualified']
    for p,h in geometry['sources'].items():assert digest(p)==h,p
    capture_path=HERE/f'capture-{index:02d}.json';capture=read(capture_path)
    folder=HERE/f'numeric-{index:02d}';artifacts=[]
    for kind,path in [('observations',folder/'tracks.json'),('candidates',folder/'banks/manifest.json'),('candidates',folder/'banks/banks.npz')]:
        artifacts.append(dict(kind=kind,path=str(path),sha256='sha256:'+digest(path)))
    entry=dict(session_id=capture['session_id'],manifest_sha256=capture['input_manifest_sha256'],artifacts=artifacts)
    document=fast.load_documents(dict(config=geometry['config'],inputs=[entry]))[0]
    sources={str(p):digest(p) for p in (Path(__file__),proof,geometry_path,capture_path,ROOT/'tools/ds7_fast_baseline_adapter.py',ROOT/'tools/ds7_baseline_adapter.py')}
    sources.update({a['path']:a['sha256'].removeprefix('sha256:') for a in artifacts})
    return document,geometry['config'],np.array(geometry['fit']['x'][:2]),capture,entry,sources
