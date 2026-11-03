import numpy as np
from ds23_joint_gain_controls import triple_segments,frame_coefficients


def test_triple_support_never_reuses_a_source_or_target_frame():
    frame=np.repeat(np.arange(4),100)
    g=[dict(frame=frame.copy(),valid=np.ones(400,bool)) for _ in range(3)]
    g[2]['frame'][100:200]=0
    segments=triple_segments(g)
    assert len(segments)==3
    for geometry in g:
        ids=[geometry['frame'][s[0]] for s in segments]
        assert len(set(ids))==len(ids)


def test_joint_extraction_separates_two_overlapping_complex_emitters():
    rng=np.random.default_rng(14);n=1000;t=np.arange(n)
    x=np.column_stack([np.exp(.23j*t),np.exp(.27j*t)])
    truth=np.array([2+1j,-.4+3j]);y=x@truth+(.01*rng.normal(size=n)+.01j*rng.normal(size=n))
    c,cov=frame_coefficients(y,x,[np.arange(n)])
    assert np.max(abs(c[0]-truth))<.003
    assert np.linalg.eigvalsh(cov[0]).min()>0
