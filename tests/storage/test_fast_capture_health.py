import json
from leo.storage.fast_capture_health import checkpoint_health
from leo.contracts.digests import canonical_digest


def test_health_preserves_invalid_and_live_checkpoint_bytes(tmp_path):
    good=tmp_path/'live';good.mkdir();bad=tmp_path/'abandoned';bad.mkdir()
    (good/'run.json').write_text(json.dumps(dict(schema_version=1,kind='continuous_short_window_run',
        run_id='live',configuration={},configuration_sha256=canonical_digest({}),host='radio',serial='serial',
        state='running',updated_utc_ns=123)))
    (bad/'run.json').write_text('{invalid')
    before={p.name:(p/'run.json').read_bytes() for p in (good,bad)}
    facts={r['run_id']:r for r in checkpoint_health(tmp_path)}
    assert facts['live']['state']=='running' and facts['live']['updated_utc_ns']==123
    assert facts['abandoned']['state']=='invalid'
    assert before=={p.name:(p/'run.json').read_bytes() for p in (good,bad)}
