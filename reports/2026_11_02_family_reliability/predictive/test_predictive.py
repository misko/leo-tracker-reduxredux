import importlib.util
from pathlib import Path
from types import SimpleNamespace
import numpy as np

spec=importlib.util.spec_from_file_location('predictive',Path(__file__).with_name('predictive.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def test_normalized_density_matches_dense_covariance():
    rng=np.random.default_rng(14);n=23;y=rng.normal(size=n);s=rng.uniform(.2,2,n);u=rng.normal(size=(n,4))
    c=np.diag(s*s)+u@u.T
    expected=y@np.linalg.solve(c,y)+np.linalg.slogdet(c)[1]+n*np.log(2*np.pi)
    assert np.isclose(m.normalized_gaussian(y,s,u)['negative_twice_log_density'],expected)


def test_native_whole_group_guard_and_determinism():
    t=np.tile(np.arange(300.)+.1,2);ids=[f'{k}' for k in range(len(t))]
    p=SimpleNamespace(flat_times=t,keep=np.ones(len(t),bool),members=[0],
        scan=SimpleNamespace(tracks=[dict(observation_ids=ids)]),
        rows=[dict(candidate_norad=1)],slices=[slice(0,len(t))])
    aa=m.partitions(p);bb=m.partitions(p);blocks=np.floor(t/5).astype(int)
    assert len(aa)==3
    for a,b in zip(aa,bb):
        assert np.array_equal(a['held_ids'],b['held_ids'])
        assert not np.any(a['train']&a['test'])
        assert not np.isin(blocks[a['train']],a['guard_blocks']).any()
        assert np.array_equal(a['test'][:300],a['test'][300:])
