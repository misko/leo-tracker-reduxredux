from probe_ds23_iteration014_cross_band_step import supporting_curves


def test_other_band_can_support_receiver_event_only_with_independent_RF_gain_and_sign():
    controls=[dict(channel=1,gain=3.,amplitude_hz=-300.),dict(channel=6,gain=3.,amplitude_hz=-300.),
              dict(channel=2,gain=-1.,amplitude_hz=-300.),dict(channel=3,gain=3.,amplitude_hz=300.)]
    target=dict(channel=5,mean_difference_hz=200.,independent_original_parent_curves=controls)
    assert supporting_curves(target)==[controls[0]]
