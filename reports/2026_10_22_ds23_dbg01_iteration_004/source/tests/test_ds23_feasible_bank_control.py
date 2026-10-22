from control_ds23_dbg01_feasible_bank import choose


def test_invalid_low_loss_branch_cannot_hide_a_qualified_RF_improvement():
    invalid=dict(paired_valid=False,arms={'c0':{'corrected_selection_loss':0.}})
    valid=dict(paired_valid=True,arms={'c0':{'corrected_selection_loss':90.}})
    selected,gain=choose([invalid,valid],100.,2.)
    assert selected is valid and gain==10.
    assert choose([invalid,valid],91.,2.)[0] is None
