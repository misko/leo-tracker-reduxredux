"""Verify that held outcomes cannot enter the primitive schedule or Graph fit."""

from copy import deepcopy

from deferred_family_primitive_challenge import OPPORTUNITY_FIELDS, partition


def row(start, receiver, freq, index):
    return dict(visit_index=index, valid_start_counter=start, receiver_id=receiver,
                actual_rf_hz=freq, channel=1, candidates=[dict(fractional_tracking_cfo_hz=300)])


def native():
    probes = [row(102, 1, 100, 0), row(108, 0, 100, 1), row(125, 1, 200, 2),
              row(105, 1, 200, 3), row(119, 0, 200, 4)]
    return dict(clock_anchor=dict(sample_counter=100), source=dict(probes=probes))


def test_partition_withholds_every_held_outcome_and_guards_all_lanes():
    packet = native()
    held, train, embargo = partition(packet, 1, 100, 10, 10, 1)
    assert [row["visit_index"] for row in held] == [0]
    assert [row["visit_index"] for row in train] == [2]
    assert sorted(row["visit_index"] for row in embargo) == [1, 3, 4]
    assert set(held[0]) == set(OPPORTUNITY_FIELDS)


def test_held_outcome_perturbation_cannot_change_the_split_or_training():
    packet = native()
    edited = deepcopy(packet)
    edited["source"]["probes"][0]["candidates"] = []
    edited["source"]["probes"][3]["candidates"][0]["fractional_tracking_cfo_hz"] = -1000
    assert partition(edited, 1, 100, 10, 10, 1) == partition(packet, 1, 100, 10, 10, 1)
