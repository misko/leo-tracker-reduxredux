from copy import deepcopy

from tools.pipeline_eval.variants import negative_rescue as policy


def probe(*flags, receiver=0, source="stock"):
    return dict(
        receiver_id=receiver,
        valid_start_counter=400,
        candidates=[
            {policy.GATE: flag, "candidate_rank": rank, "source": source}
            for rank, flag in enumerate(flags)
        ],
    )


def test_only_negative_to_positive_changes_a_complete_packet():
    stock = probe(False, True, False)
    other = probe(True, True, True, source="diff")
    negative = probe(False, False)
    empty = probe(source="diff")
    data = deepcopy([stock, other, negative, empty])
    assert policy.select(stock, other) is stock
    assert policy.select(stock, empty) is stock
    assert policy.select(negative, empty) is negative
    assert policy.select(negative, other) is other
    assert [stock, other, negative, empty] == data


def test_stereo_cost_charges_only_one_second_call_if_either_receiver_misses():
    a, b = probe(True), probe(True, receiver=1)
    negative_a, negative_b = probe(), probe(False, receiver=1)
    assert not policy.misses((a, b))
    assert policy.misses((a, negative_b))
    assert policy.misses((negative_a, b))
    assert policy.misses((negative_a, negative_b))
