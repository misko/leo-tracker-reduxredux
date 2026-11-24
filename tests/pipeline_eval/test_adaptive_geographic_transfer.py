import pytest

from leo.contracts.digests import canonical_digest
from reports.ALGO08.v3 import adaptive_geographic_transfer as study


@pytest.mark.parametrize("digest,terminal,accepted", [(True, "known", True), (False, "known", False), (True, "other", False)])
def test_transfer_checks_the_sealed_scientific_map_and_terminal(monkeypatch, tmp_path, digest, terminal, accepted):
    grid = dict(complete=True, coarse_size=9, local_size=7, binding={"terminal_sha256": "known"}, elapsed_seconds=0.1)
    scientific = canonical_digest({"complete": True, "coarse_size": 9, "local_size": 7})
    monkeypatch.setattr(study.FastStandardAnalysisStore, "position_grid", lambda self, run: grid)
    monkeypatch.setattr(study, "screen", lambda document: {"fidelity": True})
    receipt = {"run_id": "example", "terminal_sha256": terminal}
    if accepted:
        assert study.audit(tmp_path, receipt, scientific) == {"fidelity": True}
    else:
        with pytest.raises(ValueError):
            study.audit(tmp_path, receipt, scientific if digest else "changed")
