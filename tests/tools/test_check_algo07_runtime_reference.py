"""The saved-policy parity gate must reject a changed scientific result."""

import copy
import json

from algo07_science.policy import POLICY

from leo.cli.algo07_profile import digest, freeze
from tools import check_algo07_runtime_reference as checker


def test_policy_replay_detects_endpoint_regression(tmp_path, monkeypatch):
    receipts = tmp_path / "receipts"
    receipts.mkdir()
    receipt = receipts / "DS26-0002.json"
    baseline = {
        arm: dict(x=[1.0, 2.0], objective=40.0, associated=30, error_m=300.0, rms_hz=50.0)
        for arm in ("c0", "fitted_c")
    }
    receipt.write_text(json.dumps(dict(baseline=baseline, records={"combined": []})))
    audit = tmp_path / "audit.json"
    audit.write_text(
        json.dumps(
            dict(
                source_sha256={str(receipt): digest(receipt)},
                outcomes=[
                    dict(case="DS26-0002", policy=POLICY, selected=None, final=baseline, review=[])
                ],
            )
        )
    )
    spec = tmp_path / "spec.json"
    spec.write_text(json.dumps(dict(files=[dict(path=str(p)) for p in (receipt, audit)])))
    manifest = tmp_path / "frozen.json"
    freeze(spec, manifest)
    assert checker.check(manifest, audit)["passed"] is True
    select = checker.select

    def wrong_position(*args):
        result = copy.deepcopy(select(*args))
        result["final"]["fitted_c"]["x"][0] += 1
        return result

    monkeypatch.setattr(checker, "select", wrong_position)
    failed = checker.check(manifest, audit)
    assert failed["passed"] is False
    assert failed["failures"] == [dict(case="DS26-0002", field="final")]
