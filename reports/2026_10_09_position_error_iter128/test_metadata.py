from types import SimpleNamespace

import numpy as np
from metadata import project

from leo.contracts.digests import canonical_digest


def test_projection_original_rank_anchor_and_missing_coverage():
    source = SimpleNamespace(
        input_manifest_sha256="capture",
        analysis_manifest_sha256="analysis",
        sample_rate_hz=2_500_000,
    )
    group = canonical_digest({"capture": "capture", "visit": 3, "rx": 1, "probe": 2})
    identity = canonical_digest({"group": group, "rank": 4, "analysis": "analysis"})
    data = dict(
        candidate_rank=4,
        passed_fractional_margin_gate=True,
        fractional_tracking_cfo_hz=321,
        integer_epoch_sample=123,
        fractional_epoch_offset_samples=0.25,
        acquired_cfo_hz=111,
        fractional_exact_score=0.5,
        fractional_control_score=0.1,
        fractional_margin=0.4,
    )
    candidate = SimpleNamespace(**data, model_dump=lambda **_: data)
    probe = SimpleNamespace(
        receiver_id=1, probe_index=2, probe_start_ms=120, candidates=[candidate]
    )
    product = SimpleNamespace(
        visit_index=3,
        valid_start_counter=1000,
        valid_end_counter=501000,
        probes=[probe],
        target=SimpleNamespace(channel=2, edge=SimpleNamespace(value="upper")),
        model_dump=lambda **_: {"synthetic": "product"},
    )
    prepared = SimpleNamespace(
        candidate_ids=[identity, "missing"],
        observations=SimpleNamespace(
            window_ids=[group, "missing-group"], measured_hz=np.array([321, 0])
        ),
    )
    rows, visits = project(source, prepared, [product])
    assert len(rows) == 2
    assert rows[0]["acquired_cfo_hz"] == 111
    assert rows[0]["probe_start_sample"] == 300000
    assert rows[0]["epoch_sample"] == 123 and rows[0]["offset_samples"] == 0.25
    assert rows[1]["status"] == "missing-full-candidate"
    assert visits[3]["sample_count"] == 500000
