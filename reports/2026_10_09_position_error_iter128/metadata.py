"""Public metadata-only projection. Never opens an IQ reader or orbit model."""

import argparse
import hashlib
import json
from pathlib import Path

from leo.analysis.catalogue_eligibility import exclude_labelled_starlink_debris
from leo.application.regional_position_inputs import prepare_position_windows
from leo.contracts.digests import canonical_digest
from leo.operations.tle_archive import TleArchiveReader
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
from leo.sky.propagation import parse_element_sets
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.scanner_tracking_source import ScannerTrackingInputStore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DATA = Path("/srv/bulk/leo")


def project(source, prepared, products):
    lookup = {}
    visits = {}
    for product in products:
        visits[product.visit_index] = {
            "sample_count": product.valid_end_counter - product.valid_start_counter,
            "valid_start_counter": product.valid_start_counter,
            "product_sha256": canonical_digest(product.model_dump(mode="json")),
        }
        for probe in product.probes:
            group = canonical_digest(
                {
                    "capture": source.input_manifest_sha256,
                    "visit": product.visit_index,
                    "rx": probe.receiver_id,
                    "probe": probe.probe_index,
                }
            )
            for candidate in probe.candidates:
                candidate_id = canonical_digest(
                    {
                        "group": group,
                        "rank": candidate.candidate_rank,
                        "analysis": source.analysis_manifest_sha256,
                    }
                )
                lookup[candidate_id] = (group, product, probe, candidate)
    windows = []
    for index, (window_id, candidate_id) in enumerate(
        zip(prepared.observations.window_ids, prepared.candidate_ids, strict=True)
    ):
        row = {"window_id": window_id, "candidate_id": candidate_id, "observation_index": index}
        if candidate_id not in lookup:
            row.update(status="missing-full-candidate")
            windows.append(row)
            continue
        group, product, probe, c = lookup[candidate_id]
        assert group == window_id
        assert c.passed_fractional_margin_gate
        assert c.fractional_tracking_cfo_hz == prepared.observations.measured_hz[index]
        row.update(
            status="metadata-ready",
            visit=product.visit_index,
            receiver=probe.receiver_id,
            channel=product.target.channel,
            edge=product.target.edge.value,
            probe_index=probe.probe_index,
            probe_start_sample=probe.probe_start_ms * source.sample_rate_hz // 1000,
            probe_count=source.sample_rate_hz // 50,
            epoch_sample=c.integer_epoch_sample,
            offset_samples=c.fractional_epoch_offset_samples,
            acquired_cfo_hz=c.acquired_cfo_hz,
            original_cfo_hz=c.fractional_tracking_cfo_hz,
            original_exact=c.fractional_exact_score,
            original_control=c.fractional_control_score,
            original_margin=c.fractional_margin,
            original_passed=c.passed_fractional_margin_gate,
            candidate_sha256=canonical_digest(c.model_dump(mode="json")),
        )
        windows.append(row)
    return windows, visits


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label")
    parser.add_argument("--output", default="metadata-v2")
    args = parser.parse_args()
    authority = ROOT / "reports/2026_10_09_position_error_iter110/protocol.json"
    frozen = json.loads(authority.read_text())
    assert len(frozen["members"]) == 12
    destination = HERE / args.output
    destination.mkdir(exist_ok=True)
    tracking = ScannerTrackingInputStore(DATA)
    captures = AdaptiveHopIqStore(DATA, read_only=True)
    analyses = AdaptiveHopAnalysisStore(DATA, read_only=True)
    try:
        for binding in frozen["members"]:
            member = binding["member"]
            label = member["inventory_label"]
            if args.label and label != args.label:
                continue
            path = binding["loader_binding"].get("baseline_path") or binding["regions"]["sep50"]
            row = {
                "label": label,
                "dataset": member["dataset"],
                "session_id": member["session_id"],
                "authority_sha256": hashlib.sha256(authority.read_bytes()).hexdigest(),
                "document_path": path,
                "projection_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            }
            try:
                document_raw = (ROOT / path).read_bytes()
                expected = frozen["source_sha256"][path]
                assert hashlib.sha256(document_raw).hexdigest() == expected
                document = json.loads(document_raw)
                source = tracking.load(member["session_id"])
                assert (
                    source.input_manifest_sha256
                    == binding["loader_binding"]["effective_input_digest"]
                )
                assert source.analysis_manifest_sha256 == document["analysis_manifest_sha256"]
                prepared = prepare_position_windows(source)
                archive = TleArchiveReader(Path("/var/lib/leo/tle"))
                snapshot = archive.select_latest_before(prepared.start_utc_ns - 505_000_000_000)
                if "snapshot_sha256" in document["diagnostics"]:
                    assert snapshot.digest == document["diagnostics"]["snapshot_sha256"], (
                        "TLE metadata"
                    )
                payload, _ = exclude_labelled_starlink_debris(archive.read(snapshot))
                catalogue = parse_element_sets(payload)
                numbers = [
                    int(number)
                    for name, number in zip(
                        catalogue.names, catalogue.satellite_numbers, strict=True
                    )
                    if name.upper().startswith("STARLINK")
                ]
                evidence = canonical_digest(
                    {
                        "windows": prepared.evidence_sha256,
                        "tle": snapshot.digest,
                        "candidates": numbers,
                    }
                )
                assert evidence == document["evidence_sha256"], "composite evidence"
                assert len(prepared.candidate_ids) == document["windows"]
                capture = captures.inspect(member["session_id"])
                bound = bind_actual_visit_analysis(
                    capture.manifest.receipt,
                    input_manifest_sha256=capture.manifest_sha256,
                    probe_stride_ms=120,
                )
                with analyses.job(bound) as job:
                    windows, visits = project(source, prepared, job.published_visits())
                row.update(
                    status="complete",
                    document_sha256=expected,
                    input_manifest_sha256=source.input_manifest_sha256,
                    analysis_manifest_sha256=source.analysis_manifest_sha256,
                    evidence_sha256=evidence,
                    prepared_windows_sha256=prepared.evidence_sha256,
                    sample_rate_hz=source.sample_rate_hz,
                    receiver_ids=list(capture.manifest.receipt.plan.geometry.receiver_ids),
                    analysis_binding=bound.model_dump(mode="json"),
                    expected_observations=len(windows),
                    window_ids=list(prepared.observations.window_ids),
                    windows=windows,
                    visits=visits,
                )
            except Exception as exc:
                row.update(status="metadata-failed", error=f"{type(exc).__name__}: {exc}")
            with (destination / f"{label}.json").open("x") as stream:
                json.dump(row, stream, indent=2)
            print(
                label,
                row["status"],
                row.get("expected_observations"),
                row.get("error", ""),
                flush=True,
            )
    finally:
        tracking.close()
        captures.close()
        analyses.close()


if __name__ == "__main__":
    main()
