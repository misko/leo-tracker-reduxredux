import pytest

from reports.ALGO08.v3.progressive_primary import agrees, needs_restart, progressive


def factor(epoch=0, frequency=0, score=.10):
    return ((0, epoch, .5, frequency, score, 0.),)


@pytest.mark.parametrize("first,repeat", [((), True), (factor(score=.049), True),
                                         (factor(score=.05), False), (factor(score=float("nan")), True)])
def test_second_call_replaces_first_only_on_restart(first, repeat):
    calls = []

    def search(arm):
        calls.append(arm)
        return (first if arm == "8ms" else factor(37)), 17

    result, original, cpu, retried = progressive(search)
    assert calls == (["8ms", "12ms"] if repeat else ["8ms"])
    assert (result, original, cpu, retried) == (factor(37) if repeat else first, first, 17, repeat)


def test_scoring_uses_wrapped_time_and_frequency():
    assert agrees((), ())
    assert not agrees((), factor())
    assert agrees(factor(), factor(13335, -250))
    assert not agrees(factor(), factor(13336))
    assert not agrees(factor(), factor(0, 250.01))


def test_rejects_an_unexpected_second_short_factor():
    with pytest.raises(ValueError):
        needs_restart(factor() * 2)
