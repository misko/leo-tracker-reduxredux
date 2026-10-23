import numpy as np

from probe_ds23_iteration013_shared_step import contexts,choose


def test_step_contexts_cannot_join_nonspanning_or_other_band_sources():
    track=lambda ch:dict(receiver=1,channel=ch,times=np.arange(10.))
    lookup={'focus':track(7),'good':track(6),'low':track(2)}
    trials=[dict(additions=[dict(component=k) for k in keys],added_curved_points=n) for keys,n in [(['focus'],10),(['focus','good'],20),(['focus','low'],20)]]
    result=contexts(trials,dict(component='focus',receiver=1,channel=7,time_s=5.),lookup)
    assert [r['added_curved_points'] for r in result]==[20,10]


def test_more_points_cannot_override_failed_gates_or_penalized_RF_acceptance():
    trial=lambda n,score,accepted:dict(added_curved_points=n,arms={'c0':dict(negative_twice_elbo=score)},accepted=accepted,kind='band')
    rows=[trial(100,0,False),trial(20,50,True),trial(20,40,True),trial(10,1,True)]
    assert choose(rows) is rows[2]
