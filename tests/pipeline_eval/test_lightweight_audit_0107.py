from pathlib import Path

import pytest


def test_semantic_parity_discards_only_named_audit_timers(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).parents[2]/"reports/ALGO08/v3"))
    from lightweight_audit_0107 import audited_payload

    clock = dict(wall_ns=17, cpu_ns=14, input_blocks=2)
    member = dict(map="original", counts={"full": 8, "prefix": 19},
                  **{name: clock.copy() for name in ("auth", "metadata", "setup", "span_decode", "map_file")})
    audit = dict(setup=dict(cpu_s=.01, elapsed_s=.012), members=[member], binary_sha256="retained")
    assert audited_payload(audit) == dict(members=[dict(map="original", counts={"full": 8, "prefix": 19})],
                                         binary_sha256="retained")
    member["auth"]["unexpected_status"] = True
    with pytest.raises(ValueError, match="stopwatch"):
        audited_payload(audit)
