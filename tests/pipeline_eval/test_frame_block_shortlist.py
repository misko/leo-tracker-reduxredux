from math import ceil, floor

from reports.ALGO08.v3 import frame_block_shortlist as trial


def test_each_pair_fir_encloses_original_planes_on_original_tiles():
    width = ceil(2_500_000/750) + 128*44//4 - 1
    for origin, (lo, hi) in ((0, trial.EARLY), (6, trial.LATE)):
        starts = [rounding(frame*10_000/3) + 88//4 for frame in (origin, origin+1)
                  for rounding in (floor, ceil)]
        assert min(starts) >= lo and max(starts) + width <= hi
        assert (lo-10) % 4 == (hi-10) % 4 == 0
        assert (hi-1)*4+40 < 120_000


def test_joint_match_wraps_pilot_time_but_never_uses_unsigned_frequency():
    factor = (0, 13332, 0.25, -160_000., .5, .1)
    assert trial.close_to(0, -159_900., factor, 2, 250)
    assert not trial.close_to(0, 159_900., factor, 2, 250)
    assert not trial.close_to(5, -159_900., factor, 2, 250)


def test_combined_ledger_charges_anchor_and_live_empty_retry(monkeypatch):
    monkeypatch.setattr(trial, "REPEATS", 1)
    factor = ((0, 19, .1, -140_000., .4, .2),)
    rows = [dict(repeat=0, kind="full", anchor=factor, anchor_clock=(90, 91)),
            dict(repeat=0, kind="short_primary", stock=factor, candidate=(), policy=factor,
                 direct_clock=(100, 101), policy_clock=(165, 166), proposal_and_verify=(60, 61),
                 oracle_verification_ns=20, proposal_ns=23, plain_clock=(110, 111), plain_exact=True, seeds=[])]
    summary = trial.summarize(rows, True)
    counts, = summary["repeats_ns"]
    assert counts["direct"] == 190 and counts["live"] == 255
    assert counts["tolerance_repair"] == counts["byte_repair"] == 250
    assert counts["oracle"] == 110 and counts["free_winner_after_proposal"] == 133
    assert summary["counts"]["policy_match"] == 1 and summary["counts"]["empty_retry"] == 1
