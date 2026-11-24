import json

import pytest

from reports.ALGO08.v3.ds30_evidence_transfer import ARMS, choose_prospective, classify, layer, measure


def factor(hz, t=0):
    return dict(fractional_tracking_cfo_hz=hz, integer_epoch_sample=1000, fractional_epoch_offset_samples=t,
                passed_fractional_margin_gate=True, candidate_rank=0, fractional_margin=1.)


def test_signed_and_wrapped_match_categorization():
    a = factor(-1200)
    assert classify(a, factor(-950, 40_000/3+1.75)) == ("same_carrier", (250, 1.75))
    assert classify(a, factor(-950, 40_000/3+2.01))[0] == "epoch_only"
    assert classify(a, factor(-949.99, 0))[0] == "signed_shift"
    assert classify(a, factor(-1200+1/4.4e-6, 0))[0] == "signed_shift"
    assert classify(a, None)[0] == "candidate_empty"
    assert classify(None, a)[0] == "sparse_only"
    assert classify(None, None)[0] == "both_empty"


def test_owner_claim_denominators_and_missing_owner_rows():
    rows = [("a", "candidate_empty", None), ("b", "sparse_only", None),
            ("c", "signed_shift", None), ("d", "same_carrier", (6, 2))]
    candidate = dict.fromkeys(ARMS, {"b": (4, 'conditional'), "c": (4, 'conditional')})
    stock = dict.fromkeys(ARMS, {"a": (4, 'conditional'), "c": (19, 'predictive')})
    data = layer(rows, {})
    assert (data['installed_positive'], data['candidate_positive'], data['both_positive']) == (3,3,2)
    assert data['same_carrier_hz_rms'] == 6
    assert data['same_carrier_epoch_rms'] == 2
    partial = layer(rows, {'successor': candidate}, arm='c0')
    assert partial['owners']['installed'] is None
    assert partial['jointly_owned'] is None
    assert partial['owners']['successor']['states']['sparse_only'] == 1
    result = layer(rows, {'installed': stock, 'successor': candidate}, arm='fitted_c')
    assert result['owners']['installed']['states']['candidate_empty'] == 1
    assert result['jointly_owned'] == {'shared_ids': 1, 'shared_satellite': 0, 'shared_satellite_role': 0}
    with pytest.raises(ValueError, match='no admitted passed factor'):
        layer(rows, {'installed': candidate}, arm='fitted_c')


def test_signed_opportunity_join_and_scheduled_anchor(tmp_path):
    row = dict(edge='lower', channel=3, actual_rf_hz=11_200_000_000)
    probes = [dict(row, visit_index=v, valid_start_counter=2_000_000*v, receiver_id=r,
                   candidates=[factor(-1000.)]) for v in range(9) for r in (0,1)]
    source = dict(session_id='clock', input_manifest_sha256='input', raw_recording_authority_digest='raw',
                  capture_start_utc_ns=123, probes=probes)
    packet = dict(source=source, last_sample_counter=1e9, clock_anchor='signature', delivery_clocks=[],
                  provenance=dict(excluded_windows=[]))
    report = measure(packet, packet, {})
    assert report['anchor']['rx0']['lanes'] == 2 and report['anchor']['rx1']['lanes'] == 2
    assert report['short']['both']['states']['same_carrier'] == 14
    different_clock = dict(packet, last_sample_counter=2e9)
    with pytest.raises(ValueError, match='chronology'):
        measure(packet, different_clock, {})


def test_prospective_uses_first_available_pair_without_reading_results(tmp_path):
    def ready(case, *, both=True):
        case_root = tmp_path/'cases'/case
        for role in ('installed','successor') if both else ('installed',):
            attempt = case_root/role/'attempt-000001'
            native = attempt/'publication/fast-scan-automatic-work/r/detections.json'
            native.parent.mkdir(parents=True)
            native.write_bytes(b'not consulted for enrolment')
            (attempt/'result.json').write_bytes(b'not consulted for enrolment')
        (case_root/'pair.json').write_text(json.dumps(dict(generation=1, state='observed_pair', verified_pair=True)))

    ready('DS30-0183')
    ready('DS30-0105', both=False)
    assert choose_prospective(tmp_path)[0] == 'DS30-0183'
    ready('DS30-0244')
    case, availability = choose_prospective(tmp_path)
    assert case == 'DS30-0244'
    assert 'DS30-0183' not in availability
    assert availability['DS30-0105']['attempts']['successor'] == dict(result=False, native=False)
