import pytest

from reports.ALGO08.v3.full_short_factor_contrast import CELLS, census, compatible, strata, substituted


def measurement(epoch, hz, margin=.083):
    return dict(integer_epoch_sample=int(epoch), fractional_epoch_offset_samples=epoch-int(epoch),
                fractional_tracking_cfo_hz=hz, fractional_margin=margin, passed_fractional_margin_gate=True)


def packets(a, b):
    def packet(factors):
        probes = [dict(visit_index=i//2, valid_start_counter=200000*(i//2), receiver_id=i % 2, edge="lower",
                       channel=1, actual_rf_hz=11_000_000_000, candidates=[] if f is None else [f])
                  for i, f in enumerate(factors)]
        return dict(source=dict(probes=probes, session_id="signed-session"), provenance=dict(window_count=len(probes)//2))

    return packet(a), packet(b)


def test_match_uses_wrapped_epoch_and_signed_cfo():
    anchor = measurement(13_333.3, -30_000)
    assert compatible(anchor, measurement(1, -29_750))
    assert not compatible(anchor, measurement(3, -29_750))
    assert not compatible(anchor, measurement(1, 30_000))
    assert not compatible(anchor, measurement(1, -29_749.9))


def test_substitutions_preserve_single_earned_tuple_and_both_radios():
    a, b, c, d, e, f = (measurement(n, hz) for n, hz in [(39, -1221), (40, -1200), (33, 972), (33, -972), (15, 412), (44, -22)])
    source = [a, c, e, None, None, None]
    mixed = [b, d, None, f, None, None]
    p, q = packets(source, mixed)
    rows = strata(p, q)

    def chosen(cell):
        return [lane["candidates"][0] if lane["candidates"] else None for lane in substituted(rows, cell)]

    assert chosen("stock") == source and chosen("candidate") == mixed
    assert chosen(CELLS[0]) == [b, c, e, None, None, None]
    assert chosen(CELLS[1]) == [b, None, None, None, None, None]
    assert chosen(CELLS[2]) == [a, d, None, f, None, None]
    assert census(rows)["counts"]["rx1/anchor"]["changed_identity"] == 1


def test_signed_scope_and_duplicate_factor_fail_closed():
    found = measurement(4, -42.)
    p, q = packets([None, None], [found, None])
    q["source"]["probes"][0]["actual_rf_hz"] += 1
    with pytest.raises(ValueError, match="lane changed identity"):
        strata(p, q)
    p, q = packets([None, None], [found, None])
    q["source"]["probes"][0]["candidates"].append(found)
    with pytest.raises(ValueError, match="single genuine selected factor"):
        strata(p, q)
