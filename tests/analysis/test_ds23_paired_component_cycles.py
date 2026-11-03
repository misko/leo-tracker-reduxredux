from inventory_ds23_paired_component_cycles import paired_cycles, PERIOD


def peak(epoch, frequency, margin=.8):
    return dict(integer_epoch_sample=epoch, fractional_epoch_offset_samples=0.,
        fractional_tracking_cfo_hz=frequency, passed_fractional_margin_gate=True,
        fractional_margin=margin)


def test_cycles_require_four_distinct_native_peaks():
    first = [peak(100, 12000), peak(200, 18000)]
    second = [peak(100, 12010), peak(200, 18010)]
    cycles = paired_cycles(first, second)
    assert len(cycles) == 1
    assert cycles[0]['epoch_separation_samples'] == [100, 100]
    assert not paired_cycles(first[:1], second)


def test_cycles_reject_alias_duplicate_and_epoch_duplicate_components():
    first = [peak(100, 12000), peak(200, 12000+PERIOD)]
    second = [peak(100, 12010), peak(200, 12010+PERIOD)]
    assert not paired_cycles(first, second)
    assert not paired_cycles([peak(100, 12000), peak(105, 18000)],
        [peak(100, 12010), peak(105, 18010)])


def test_cycles_reject_weak_or_misaligned_common_components():
    assert not paired_cycles([peak(100, 12000), peak(200, 18000)],
        [peak(101, 12010), peak(200, 18010)])
    assert not paired_cycles([peak(100, 12000), peak(200, 18000, .2)],
        [peak(100, 12010), peak(200, 18010)])


def test_explicit_lower_margin_inventory_preserves_native_gate_and_geometry():
    first=[peak(100,12000),peak(200,18000,.15)]
    second=[peak(100,12010),peak(200,18010,.12)]
    assert not paired_cycles(first,second)
    assert len(paired_cycles(first,second,minimum_margin=.1))==1
    second[1]['passed_fractional_margin_gate']=False
    assert not paired_cycles(first,second,minimum_margin=.1)
