import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'reports/ALGO08/v3'))

from raw_cfo_north_score import owner_summary
from raw_cfo_north_trial import ORDER, native_file, verified_packet


def test_north_owner_receipt_checks_original_opportunities_and_changes():
    rows = [['o1',10,'conditional'],['o2',20,'predictive']]
    joined = owner_summary(rows, {'o1','o2','o3'}, {'o2','o3'})
    assert joined['count'] == 2
    assert joined['owned_updated_cfo'] == 1
    assert joined['by_role'] == {'conditional':1,'predictive':1}
    reversed_rows = owner_summary(rows[::-1], {'o1','o2'}, {'o2'})
    assert reversed_rows['bound_sha256'] == joined['bound_sha256']
    assert reversed_rows['ordered_sha256'] != joined['ordered_sha256']
    with pytest.raises(ValueError,match='unique original'):
        owner_summary(rows + [rows[0]], {'o1','o2'}, {'o2'})
    with pytest.raises(ValueError,match='unique original'):
        owner_summary(rows, {'o1'}, {'o2'})


def test_saved_refined_port_rejects_the_wrong_recipe_before_publication(tmp_path, monkeypatch):
    import empty_bootstrap
    import full_short_run
    from leo.contracts.digests import canonical_digest
    import short_cfo_raw

    monkeypatch.setattr(full_short_run,'checked_recipe',lambda:{'original':True})
    monkeypatch.setattr(short_cfo_raw,'recipe',lambda original,pin:dict(original,parent=pin,step=1.0))
    monkeypatch.setattr(empty_bootstrap,'bind_native',lambda *_a,**_kw:None)
    work = tmp_path/ORDER[0]/'fast-scan-automatic-work'/'scoped'
    work.mkdir(parents=True)
    source = dict(source=dict(raw_recording_authority_digest='authority'))
    (work/'detections.json').write_text(json.dumps(source,separators=(',',':'),sort_keys=True))
    raw = tmp_path/ORDER[0]
    original_recipe = short_cfo_raw.recipe(full_short_run.checked_recipe(),full_short_run.RECIPE_SHA)
    receipt = dict(native_sha256=canonical_digest(source),receiver_recipe=original_recipe,
                   detector_recipe_sha256=canonical_digest(original_recipe),raw_acquisitions=1,
                   verified_handoffs=1,causal_cutoff_utc_ns=2)
    info = raw/'unified-short-bootstrap.json'
    info.write_text(json.dumps(receipt))
    request = dict(session='session',inventory='inventory',cutoff_utc_ns=2,authority='authority')
    path, found, witness = verified_packet(raw,request)
    assert path == native_file(raw)
    assert found == source
    assert witness == receipt
    receipt['receiver_recipe']['step'] = 2.0
    info.write_text(json.dumps(receipt))
    with pytest.raises(ValueError,match='genuine raw handoff'):
        verified_packet(raw,request)
