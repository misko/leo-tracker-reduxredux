"""Analyze one qualified 300s canary through production ports, without RF."""

import json
import signal
import sys
import time
from pathlib import Path

from leo.application.persistent_hop_analysis_v2 import PersistentHopAnalysisServiceV2
from leo.presentation.persistent_hop_analysis_v2 import render_persistent_hop_analysis_pngs_v2
from leo.storage.persistent_hop import PersistentHopIqStore
from leo.storage.persistent_hop_analysis_source import PersistentHopAnalysisInputStore
from leo.storage.persistent_hop_analysis_v2 import PersistentHopAnalysisStoreV2

capture_report = json.loads(Path(sys.argv[1]).read_text())
root, output = Path(sys.argv[2]), Path(sys.argv[3])
if capture_report["status"] != "capture_passed" or output.exists():
    raise ValueError("requires a qualified capture and a fresh output report")
session_id = capture_report["session_id"]
report = dict(session_id=session_id, status="starting", started_utc_ns=time.time_ns())


def deadline(_signum, _frame):
    raise TimeoutError("analysis exceeded its 30-minute bound; completed sweeps are checkpointed")


signal.signal(signal.SIGALRM, deadline)
signal.alarm(1800)
try:
    captures = PersistentHopIqStore.open_read_only(root)
    capture = captures.verify(session_id)
    assert capture.manifest_sha256 == capture_report["manifest_sha256"]
    products = PersistentHopAnalysisStoreV2(root)
    with products.worker_lock() as acquired:
        if not acquired:
            raise RuntimeError("canary analysis worker lease is busy")
        service = PersistentHopAnalysisServiceV2(
            inputs=PersistentHopAnalysisInputStore(captures),
            products=products,
            renderer=render_persistent_hop_analysis_pngs_v2,
            probe_stride_ms=120,
            maximum_workers=2,
        )
        manifest = service.analyze_session(session_id)
        assert manifest.schema_version == 3
        assert manifest.sample_rate_hz == manifest.bandwidth_hz == 10_000_000
        assert manifest.visit_count == len(capture.manifest.receipt.visits)
        chunks = products.published_chunks(session_id)
        assert sum(chunk.visit_count for chunk in chunks) == manifest.visit_count
        assert all(chunk.receiver_ids == capture.manifest.receiver_ids for chunk in chunks)
        assert all(products.artifact(session_id, item.name) for item in manifest.artifacts)
        report.update(status="analysis_passed", manifest=manifest.model_dump(mode="json"))
except BaseException as error:
    report.update(status="failed", error=f"{type(error).__name__}: {error}")
    raise
finally:
    signal.alarm(0)
    report["finished_utc_ns"] = time.time_ns()
    output.write_text(json.dumps(report, indent=2) + "\n")
