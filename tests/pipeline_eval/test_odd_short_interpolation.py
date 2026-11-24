from math import remainder

import pytest

from reports.ALGO08.v3.odd_short_interpolation import (
    ADC, HERTZ, PERIOD, evaluation, interpolate, mask, nominate, signed,
)


def probe(visit, radio, counter, channel, candidates):
    return dict(visit_index=visit, receiver_id=radio, valid_start_counter=counter,
                edge="falling", channel=channel, actual_rf_hz=1.15e10+channel, candidates=candidates)


def factor(hz, phase):
    epoch = int(phase)
    return {HERTZ: hz, "integer_epoch_sample": epoch, "fractional_epoch_offset_samples": phase-epoch,
            "passed_fractional_margin_gate": True, "fractional_margin": .05, "candidate_rank": 0}


def test_mask_discards_entire_held_candidate_list_and_ignores_invalid_visits():
    poison = object()  # Any attempted winner or serialization from the held row fails.
    admitted = [(0, 1), (2, 1), (3, 2), (4, 1), (5, 2)]
    probes = [probe(visit, radio, 5_000_000*visit, ch,
                    poison if visit in (2, 5) else [factor(40, .2)])
              for visit, ch in admitted for radio in (0, 1)]
    source = dict(session_id="test", raw_recording_authority_digest="sha256:raw", probes=probes)
    native = dict(source=source, provenance=dict(excluded_windows=[dict(visit=1)],
                  detector_sha256="sha256:detector", window_count=6, processed_windows=5))
    sanitized, omitted, modes = mask(native)
    assert {row["visit"] for row in omitted.values()} == {2, 5}
    assert len(omitted) == 4 and modes == {"full": 4, "short_primary": 6}
    opportunities = signed.opportunities(sanitized)
    assert all(opportunities[key]["factor"] is None and opportunities[key]["row"]["candidates"] == []
               for key in omitted)
    assert all(row["candidates"] is poison for row in probes if row["visit_index"] in (2, 5))
    assert len([row for row in opportunities.values() if row["factor"]]) == 6


def donor(name, counter, frequency, phase, *, lift=1, ordinal=0):
    return dict(id=name, counter=counter, factor=factor(frequency, phase), lift=lift,
                short=True, piece=("track", 0), ordinal=ordinal,
                row=probe(0, 0, counter, 1, []))


def test_signed_single_branch_and_physical_phase_crossing():
    start = 1_000_000_000_000_000
    left = donor("l", start, -1000, PERIOD-2)
    right = donor("r", start+ADC, 1000, 2, ordinal=1)
    forecast, reason = interpolate(left, start+ADC//2, right)
    assert reason == "proposed"
    assert forecast["cfo_hz"] == 0
    assert forecast["lifted_cfo_hz"] == signed.ALIAS
    assert abs(remainder(forecast["arrival"], PERIOD)) < 1e-8
    assert interpolate(left, start+ADC//2, dict(right, lift=0))[1] == "ambiguous_alias_branch"
    assert interpolate(left, start+ADC//2+1, dict(right, counter=start+ADC+1))[1] == "spacing"
    bad_slope = dict(right, factor=factor(9000, .2))
    assert interpolate(left, start+ADC//2, bad_slope)[1] == "slope"


def test_final_nomination_requires_immediate_registered_same_piece_neighbors():
    l = donor("l", 0, 15, 1)
    r = donor("r", ADC, 17, 1, ordinal=1)
    held = {"m": dict(lane=("falling", 1, l["row"]["actual_rf_hz"], 0), counter=ADC//2)}
    missing = dict(id="m", row=probe(0, 0, ADC//2, 1, []), factor=None)
    rows = {"l": l, "m": missing, "r": r}
    got, reasons = nominate(held, rows, {"l": l, "r": r})
    assert got["m"]["donors"] == ["l", "r"]
    assert reasons == {"proposed": 1}
    assert nominate(held, rows, {"l": l, "r": dict(r, piece=("other", 1))})[1] == {
        "different_or_nonadjacent_piece": 1}
    another = donor("l2", ADC//4, 16, 1)
    rows = {"l": l, "l2": another, "m": missing, "r": r}
    assert nominate(held, rows, {"l": l, "r": r})[1] == {"unassigned_or_ambiguous": 1}
    with pytest.raises(ValueError, match="held candidate"):
        nominate(held, rows | {"m": dict(missing, factor=factor(10, 0))}, {"l": l, "r": r})


def test_all_omitted_denominator_keeps_empty_wrong_alias_and_uncovered_lanes():
    held = {k: dict(counter=0) for k in ("right", "empty", "alias", "uncovered")}
    proposal = dict(cfo_hz=500., arrival=3.)
    predictions = {k: proposal for k in ("right", "empty", "alias")}
    reference = {"right": dict(factor=factor(610., 4.)), "empty": dict(factor=None),
                 "alias": dict(factor=factor(500.+signed.ALIAS, 3)),
                 "uncovered": dict(factor=factor(500., 3.))}
    counts, _, _ = evaluation(held, predictions, reference)
    assert counts["installed_positive"] == 3 and counts["uncovered_positives"] == 1
    assert counts["installed_empty_proposals"] == 1
    tight = counts["windows"]["250Hz/2samples"]
    assert tight["both"] == tight["carrier_only"] == 1
    assert tight["unmatched_nominations"] == 2
    assert tight["recall"] == tight["precision"] == 1/3
