"""Bounded companion comparison publication for recent fixed/adaptive captures."""

from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import os
import time
from pathlib import Path

from leo.analysis.starlink import acquisition, glrt_refinement_prototype, pilot_methods
from leo.analysis.starlink.refinement_comparison import compare_probe, comparison_metrics
from leo.contracts.scanner_refinement import ComparisonEvidenceV1, ComparisonEvidenceV2
from leo.presentation.scanner_refinement import render_scanner_refinement
from leo.storage.analysis_worker_lock import analysis_worker_lock
from leo.storage.scanner_refinement import ScannerRefinementStore
from leo.storage.scanner_refinement_source import comparison_session_ids, comparison_source


def run_session(root: Path, session_id: str, deadline: float) -> str:
    products = ScannerRefinementStore(root, read_only=False)
    if products.status(session_id).state == "complete":
        return "complete"
    with comparison_source(root, session_id) as source:
        implementation = (
            "sha256:"
            + hashlib.sha256(
                b"".join(
                    Path(inspect.getfile(item)).read_bytes()
                    for item in (
                        compare_probe,
                        acquisition,
                        pilot_methods,
                        glrt_refinement_prototype,
                    )
                )
            ).hexdigest()
        )
        evidence = products.work(session_id)
        if evidence is None:
            evidence_type = (
                ComparisonEvidenceV2
                if source.sample_rate_hz == 10_000_000
                else ComparisonEvidenceV1
            )
            evidence = evidence_type.model_validate(
                dict(
                    session_id=session_id,
                    session_kind=source.session_kind,
                    input_manifest_sha256=source.input_manifest_sha256,
                    implementation_sha256=implementation,
                    sample_rate_hz=source.sample_rate_hz,
                    scheduled_probe_ids=source.probe_ids,
                    rows=(),
                )
            )
        if (
            evidence.implementation_sha256 != implementation
            or evidence.input_manifest_sha256 != source.input_manifest_sha256
            or evidence.scheduled_probe_ids != source.probe_ids
        ):
            raise ValueError("comparison checkpoint input binding differs")
        done = {r.probe_id for r in evidence.rows} | {f.split("|", 1)[0] for f in evidence.failures}
        for probe_id in source.probe_ids:
            if probe_id in done:
                continue
            if time.monotonic() >= deadline:
                return "partial"
            try:
                rows = compare_probe(source.read_probe(probe_id))
            except Exception as error:
                evidence = evidence.model_copy(
                    update={
                        "failures": (
                            *evidence.failures,
                            f"{probe_id}|{type(error).__name__}: {str(error)[:180]}",
                        )
                    }
                )
            else:
                evidence = evidence.model_copy(update={"rows": (*evidence.rows, *rows)})
            products.save_work(evidence)
        metrics = tuple(
            m.model_copy(update={"attempted": len(source.probe_ids)})
            for m in comparison_metrics(evidence.rows)
        )
        products.publish(evidence, metrics, render_scanner_refinement(evidence))
        return "complete"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bulk-root", type=Path, default=Path(os.environ.get("LEO_BULK_ROOT", "/srv/bulk/leo"))
    )
    parser.add_argument("--session-id")
    parser.add_argument("--maximum-seconds", type=int, choices=range(10, 301), default=180)
    args = parser.parse_args()
    started = time.monotonic()
    with analysis_worker_lock(args.bulk_root) as acquired:
        if not acquired:
            print(json.dumps({"state": "busy"}))
            return
        store = ScannerRefinementStore(args.bulk_root)
        candidates = (
            (args.session_id,) if args.session_id else comparison_session_ids(args.bulk_root)
        )
        pending = next((s for s in candidates if store.status(s).state != "complete"), None)
        if pending is None:
            print(json.dumps({"state": "idle"}))
            return
        state = run_session(args.bulk_root, pending, started + args.maximum_seconds)
        print(
            json.dumps(
                {"session_id": pending, "state": state, "seconds": time.monotonic() - started}
            )
        )


if __name__ == "__main__":
    main()
