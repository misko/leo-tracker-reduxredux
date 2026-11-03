"""Bounded saved-corpus qualification in an explicitly isolated test database.

Reads existing IQ and frozen JSON oracle results. Never opens a radio.
"""

import argparse
import json
import time
from pathlib import Path

from leo.artifacts import AnalysisArtifactStore
from leo.catalog import CatalogRepository, create_catalog_engine, create_session_factory
from leo.contracts.fast_scan import FastScanSegmentResultV1
from leo.processing.fast_scan import process_recording
from tests.postgres_support import isolated_test_schema_url


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    parser.add_argument("--oracle-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    receipts = []
    with isolated_test_schema_url(prefix="fast_scan_qualification") as database_url:
        for edge in ("lower", "upper"):
            raw = args.raw_root / f"fast8-r20-{edge}-dual-reference-300s"
            started = time.monotonic()
            report = process_recording(raw, database_url=database_url, root=args.output, workers=8)
            elapsed = time.monotonic() - started
            print(
                json.dumps(
                    {
                        "edge": edge,
                        "run_id": report["run_id"],
                        "elapsed_s": elapsed,
                        "counts": report["counts"],
                    }
                ),
                flush=True,
            )
            engine = create_catalog_engine(database_url)
            catalog = CatalogRepository(create_session_factory(engine))
            snapshot = catalog.run_seal_snapshot(report["run_id"])
            artifacts = AnalysisArtifactStore(args.output)
            windows = {
                w.visit: w
                for p in snapshot.products
                for w in FastScanSegmentResultV1.model_validate(
                    artifacts.read_json(p.logical_uri, p.digest)
                ).windows
            }
            checked = 0
            predictor_max_error = 0.0
            active = 0
            strong = 0
            with (
                args.oracle_root / "gated-full-processing" / f"{edge}-results.jsonl"
            ).open() as stream:
                for line in stream:
                    oracle = json.loads(line)
                    window = windows.pop(oracle["global_visit"])
                    assert window.iq_sha256 == oracle["iq_sha256"]
                    expected_status = (
                        "processed" if oracle["status"] == "processed" else "skipped_fast_score"
                    )
                    assert window.status == expected_status, (
                        edge,
                        window.visit,
                        window.status,
                        oracle["status"],
                    )
                    for score, reference in zip(window.scores, oracle["scores"], strict=True):
                        assert score.epoch_sample == reference["epoch_sample"]
                        for key in ("margin", "exact", "control"):
                            predictor_max_error = max(
                                predictor_max_error, abs(getattr(score, key) - reference[key])
                            )
                    if window.status == "processed":
                        for result, reference in zip(
                            window.receivers, oracle["glrt"]["glrt"]["probes"], strict=True
                        ):
                            actual = result.model_dump(mode="json")
                            assert actual["receiver_id"] == reference["receiver_id"]
                            assert actual["candidates"] == reference["candidates"], (
                                edge,
                                window.visit,
                                result.receiver_id,
                            )
                            best = max(
                                (
                                    c.fractional_margin
                                    for c in result.candidates
                                    if c.fractional_margin is not None
                                ),
                                default=-1,
                            )
                            active += int(best >= 0.025)
                            strong += int(best >= 0.1)
                        checked += 1
            assert not windows
            assert predictor_max_error < 2e-12
            before = [catalog.attempt_states(j.job_id) for j in snapshot.jobs]
            resumed = time.monotonic()
            again = process_recording(raw, database_url=database_url, root=args.output, workers=8)
            resume_s = time.monotonic() - resumed
            assert again == report
            after = [
                catalog.attempt_states(j.job_id)
                for j in catalog.run_seal_snapshot(report["run_id"]).jobs
            ]
            assert before == after
            receipt = {
                "edge": edge,
                "run_id": report["run_id"],
                "elapsed_s": elapsed,
                "resume_s": resume_s,
                "counts": report["counts"],
                "full_candidate_parity_visits": checked,
                "predictor_max_abs_error": predictor_max_error,
                "active_rx_windows": active,
                "strong_rx_windows": strong,
                "resume_new_attempts": 0,
            }
            receipts.append(receipt)
            engine.dispose()
            (args.output / "qualification.json").write_text(json.dumps(receipts, indent=2) + "\n")
            print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    main()
