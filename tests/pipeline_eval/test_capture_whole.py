from copy import deepcopy
from hashlib import sha256
from io import BytesIO

import pytest

from tools.pipeline_eval import whole_iq
from tools.pipeline_eval.qualification.capture_whole import partition
from tools.pipeline_eval.qualification.capture_whole_results import (
    decoded_records,
    parity,
    shard_records,
)


def test_partition_assigns_every_authentic_chunk_with_exclusions_as_work_only():
    chunks = [(0, 0, 3, 0), (0, 3, 6, 0), (1, 0, 3, 6), (1, 3, 6, 6)]
    dispatched = partition(chunks, {0, 1, 6, 7}, (2, 3))
    assert sorted(c for _, _, group in dispatched for c in group) == chunks
    assert [weight for _, weight, _ in dispatched] == [4, 4]
    assert dispatched == partition(chunks[::-1], {0, 1, 6, 7}, (2, 3))


def test_only_complete_authenticated_chunks_can_join_a_partition():
    chunks = [(0, 0, 2, 0), (0, 2, 4, 0)]
    visits = [dict(kind="visit", segment=0, sequence=i, visit=i) for i in range(4)]
    completed = dict(kind="chunk", segment=0, first=0, stop=2, compressed_bytes=512)
    observed, terminal = shard_records([*visits[:2], completed, visits[2]], chunks, 2, 4, "x")
    assert observed == {(0, 0): (completed, visits[:2])}
    assert terminal is None
    with pytest.raises(ValueError, match="exact assigned visit range"):
        shard_records([visits[1], visits[0], completed], chunks, 2, 4, "x")


@pytest.mark.parametrize(
    ("statuses", "claimed", "plan", "error"),
    [
        (["processed", "invalid_capture"], 1, None, None),
        (["invalid_capture", "invalid_capture"], 0, None, None),
        (["processed", "invalid_capture"], 2, None, "work ledger"),
        (["processed", "skipped_policy"], 1, None, "visit status"),
        (["invalid_capture", "invalid_capture"], 0, 1, "work ledger"),
        (["processed", "skipped_policy"], 1, 1, None),
    ],
)
def test_verified_terminal_uses_actual_exclusions_or_independent_plan(
    statuses, claimed, plan, error
):
    visits = [
        dict(kind="visit", segment=0, sequence=i, visit=10 + i, status=status)
        for i, status in enumerate(statuses)
    ]
    resources = {
        "cpus": [2],
        "memory.max": whole_iq.MEMORY,
        "memory.swap.max": 0,
        "memory.swap.current": 0,
        "memory.events.oom_kill": 0,
        "cgroup": "/test",
        "pid": 42,
        "cpu.stat.usage_usec": 10,
    }
    chunk = dict(kind="chunk", segment=0, first=0, stop=2, compressed_bytes=128)
    terminal = dict(
        kind="worker", cpu=2, count=claimed, start=resources, end=resources, source_lock_sha256="x"
    )
    records = [*visits, chunk, terminal]
    if error:
        with pytest.raises(ValueError, match=error):
            shard_records(records, [(0, 0, 2, 10)], 2, plan, "x")
    else:
        accepted, receipt = shard_records(records, [(0, 0, 2, 10)], 2, plan, "x")
        assert accepted[(0, 0)] == (chunk, visits)
        assert receipt == terminal


def test_shard_hash_and_partial_record_follow_the_worker_exit():
    data = b'{"kind":"visit"}\n{"kind"'
    digest = sha256()
    assert list(decoded_records(BytesIO(data), digest, False)) == [{"kind": "visit"}]
    assert digest.digest() == sha256(data).digest()
    with pytest.raises(ValueError, match="partial record"):
        list(decoded_records(BytesIO(data), sha256(), True))


def test_parity_records_gate_and_precision_deltas_while_requiring_physical_identity():
    probe = dict(
        visit_index=4,
        receiver_id=0,
        candidates=[dict(passed_fractional_margin_gate=True, fractional_tracking_cfo_hz=123.5)],
    )
    document = dict(
        schema_version=2,
        clock_anchor={"sample_counter": 100},
        delivery_clocks=[{}],
        last_sample_counter=105,
        source={"probes": [probe], "analysis_manifest_sha256": "old"},
        provenance=dict(
            window_count=1,
            processed_windows=1,
            invalid_capture=0,
            excluded_windows=[],
            skipped_fast_score=0,
            rf_mapping_authorities=["hypothesis"],
        ),
    )
    actual = deepcopy(document)
    actual["source"]["analysis_manifest_sha256"] = "new"
    obs = actual["source"]["probes"][0]["candidates"][0]
    obs.update(passed_fractional_margin_gate=False, fractional_tracking_cfo_hz=124.0)
    result = parity(actual, document)
    assert result["exact"] == 0
    assert result["gate_counts"]["changed_probes"] == 1
    assert result["max_absolute_field_delta"] == {"fractional_tracking_cfo_hz": 0.5}
    actual["delivery_clocks"] = []
    with pytest.raises(ValueError, match="physical clock"):
        parity(actual, document)
