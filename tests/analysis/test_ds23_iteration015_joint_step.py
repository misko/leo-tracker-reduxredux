from probe_ds23_iteration015_joint_step import valid_standalone_unions


def test_joint_event_cannot_use_an_individually_failed_addition_to_nominate_a_correction():
    def trial(names,valid,points):return dict(additions=[dict(component=n) for n in names],paired_valid=valid,added_curved_points=points)
    a=trial(['a'],True,30);b=trial(['b'],True,20);bad=trial(['c'],False,50);joint=trial(['a','b'],False,50)
    assert valid_standalone_unions([a,b,bad,joint,trial(['a','c'],False,80),trial(['a','b'],True,50)])==[joint]
