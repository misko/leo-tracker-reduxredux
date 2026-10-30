from report_predictive_margin_sensitivity import worst_replayed_slacks


def test_replay_report_keeps_worst_duplicate_gate_not_last_value():
    row=dict(exact_incumbent_family_replays=[dict(all_gate_slacks={'slope':-.01,'rms':.5}),
        dict(all_gate_slacks={'slope':.1,'rms':.4})])
    assert worst_replayed_slacks(row)=={'slope':-.01,'rms':.4}
