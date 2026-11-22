from tools.pipeline_eval.variants.carrier_continuation import Continuation
from tools.pipeline_eval.variants.experimental.continuation_schedule import inspect


def row(counter, rx=0, ch=1, hz=1_000, rf=10_800_000_000):
    return dict(valid_start_counter=counter, receiver_id=rx, channel=ch, actual_rf_hz=rf,
                candidates=[dict(fractional_tracking_cfo_hz=hz, fractional_margin=1., candidate_rank=1)])


def test_limits_and_independent_lanes_keep_the_three_supporting_visits():
    probes = [row(0), row(100_000, rx=1), row(200_000), row(300_000), row(3_999_999)]
    needed, pub = inspect(probes)
    assert not needed and not pub
    probes += [row(4_000_000), row(89_000_000), row(99_000_000, rf=10_900_000_000)]
    needed, pub = inspect(probes)
    assert pub == {5} and needed == {0, 2, 3, 4, 5}
    def run(skip):
        continuation = Continuation()
        return [continuation.select(dict(p, candidates=[] if i in skip else p["candidates"]))[1]
                for i, p in enumerate(probes)]
    assert run(set()) == run(set(range(len(probes))) - needed)


def test_only_last_twelve_visits_can_supply_old_enough_history():
    too_recent = [row(0)] + [row(9_000_000+i*10) for i in range(13)]
    _, pub = inspect(too_recent)
    assert 12 in pub and 13 not in pub
    eight_seconds = [row(t) for t in (0, 79_000_000, 79_100_000, 80_000_000)]
    assert inspect(eight_seconds)[1] == {3}
    eight_seconds[-1] = row(80_000_001)
    assert not inspect(eight_seconds)[1]
