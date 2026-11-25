from copy import deepcopy

import held_shrink_0019 as trial
import pytest


def packet():
    factor = dict(fractional_tracking_cfo_hz=-3000., candidate_rank=0, fractional_margin=4.,
                  passed_fractional_margin_gate=True, integer_epoch_sample=70,
                  fractional_epoch_offset_samples=0.25)
    probes = [dict(receiver_id=rx, visit_index=visit, valid_start_counter=1000+visit*4000,
                   edge=0, channel=1, actual_rf_hz=11000000000, candidates=[factor.copy()])
              for visit in range(2) for rx in range(2)]
    return dict(clock_anchor={"before": 50}, delivery_clocks=[51], last_sample_counter=6000,
                provenance={"excluded_windows": []}, source=dict(probes=probes, session_id="signed",
                    input_manifest_sha256="manifest", raw_recording_authority_digest="raw",
                    capture_start_utc_ns=52))


def test_splice_keeps_every_signed_field_beside_the_selected_continuous_cfo():
    raw = packet()
    before = deepcopy(raw)
    rows = trial.signed.opportunities(raw)
    target = list(rows)[2]
    changes = {target: dict(original_hz=-3000., updated_hz=-2975., arrival=4.)}
    candidate, proof = trial.splice(raw, changes)
    after = trial.signed.opportunities(candidate)
    assert raw == before and list(after) == list(rows)
    assert after[target]["factor"] == dict(rows[target]["factor"], fractional_tracking_cfo_hz=-2975.)
    assert all(after[key] == row for key, row in rows.items() if key != target)
    assert proof["changed_by_radio"] == {"0": 1}
    assert proof["recipe"]["ordinary_graph_rebuilt_on_execution"]
    assert trial.signed.canonical(candidate) == proof["derived_native_sha256"]


def test_splice_refuses_anchor_and_mismatched_source_frequency():
    raw = packet()
    anchor, _, short, _ = trial.signed.opportunities(raw)
    for oid, old in [(anchor, -3000.), (short, -3001.)]:
        with pytest.raises(ValueError, match="original selected short factor"):
            trial.splice(raw, {oid: dict(original_hz=old, updated_hz=-2975.)})
