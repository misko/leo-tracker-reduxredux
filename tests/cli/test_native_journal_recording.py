"""Independent public-port fixtures for native recording application review."""

from __future__ import annotations

import copy
import csv
import hashlib
import json
import subprocess
import sys

import pytest

from leo.contracts.native_journal_recording import (
    NativeJournalRecordingV1,
    NativeJournalSourceBindingV1,
)
from leo.operations.native_journal_recording import (
    load_native_recording,
    recording_review,
    review_native_recording,
)


def recording():
    start = 2**60 + 1
    rows = []
    for frame in range(2):
        rows.append(
            dict(
                epoch=3,
                sequence=frame,
                frame=frame,
                delay_s=-8e-9,
                residual_hz=2.5,
                cfo_hz=125.0 if frame == 0 else 999999.0,
                coherence=0.6 if frame == 0 else 0.001,
                linearized_coherence=0.61,
                rejection=0 if frame == 0 else 16,
                supported=frame == 0,
                tag=9,
                repeat=frame,
                native_start_sample=str(start + frame * 80001),
                phase_seed_q32=0,
                phase_step_q32=123,
                sample_count=79200,
                hardware_fault=0,
                reference_sum=[str(-(2**51)), str(2**51 - 1)],
                delay_sum=["0", "1"],
                reference_prefix_integral=[str(-(2**68)), str(2**68 - 1)],
                observed_energy=str(2**53 - 1),
            )
        )
    drained = dict(
        generation=1,
        epoch=3,
        latest_index=str(start + 160000),
        status=51,
        faults=0,
        configured=2,
        admitted=2,
        late=0,
        no_space=0,
        unavailable=0,
        expired=0,
        cancelled=0,
        committed=2,
        popped=2,
        queued=0,
        high_water=2,
        cdc_drops=0,
        pacer_drops=0,
    )
    final = {
        **drained,
        "generation": 2,
        "status": 34,
        "configured": 0,
        "admitted": 0,
        "committed": 0,
        "popped": 0,
        "high_water": 0,
    }
    return dict(
        schema="starlink-glrt-native-journal-recording/v1",
        journal_sha256="a" * 64,
        journal_bytes=2000,
        epoch=3,
        epoch_scope="journal_local_requires_radio_boot_binding",
        source_rate_hz=60000000,
        pilot_samples=79200,
        pilot_center_offset_samples_twice=79199,
        timing_rule="native_start_sample + delay_s * source_rate_hz",
        frequency_reference="receiver_relative_uncalibrated",
        timing_reference="native_pilot_template",
        association_and_closure_verified=True,
        solver_replayed=False,
        original_native_iq_verified=False,
        acquisition_verified=False,
        physical_precision_qualified=False,
        descriptor_semantics="retained_intent_execution_accounted_by_heads_and_drained",
        head_count=2,
        supported_count=1,
        rejected_count=1,
        descriptors=[
            dict(
                first_frame=0,
                epoch=3,
                tag=9,
                start_sample=str(start),
                start_fraction_q16=0,
                period_q16=80001 * 65536,
                phase_step_q32_16=123 * 65536,
                phase_delta_q32_16=0,
                phase_seed_q32=0,
                repeats=2,
                expires_sample=str(start + 80001 + 79199),
            )
        ],
        measurements=rows,
        drained=drained,
        final=final,
    )


def parse(data):
    return NativeJournalRecordingV1.model_validate_json(json.dumps(data))


def test_review_preserves_large_integer_timing_and_excludes_rejected_cfo():
    model = parse(recording())
    summary, rows = recording_review(model)
    assert summary["native_sample_anchor"] == str(2**60 + 1)
    assert rows[1]["relative_scheduled_start_s"] == 80001 / 60000000
    assert rows[0]["relative_refined_start_s"] == -8e-9
    assert summary["supported_cfo_min_hz"] == summary["supported_cfo_max_hz"] == 125.0
    assert summary["head_count"] == 2 and summary["rejected_count"] == 1
    assert summary["rejection_mask_counts"] == {"16": 1}
    assert summary["runtime_outcome"] == "not_supplied_by_journal_port"
    assert not any(
        summary[k]
        for k in (
            "radio_boot_source_bound",
            "acquisition_verified",
            "solver_replayed",
            "original_native_iq_verified",
            "physical_precision_qualified",
        )
    )


@pytest.mark.parametrize(
    "corruption",
    [
        "epoch",
        "counter",
        "support_count",
        "phase",
        "start",
        "frame",
        "tag",
        "sequence",
        "fault",
        "count",
        "overflow",
        "integer_number",
        "unknown",
        "qualified",
        "nonfinite",
        "descriptor_expiry",
        "repeat",
        "boolean_counter",
        "uncleared",
        "unowned_configured",
    ],
)
def test_invalid_or_falsely_qualified_recording_is_rejected(corruption):
    value = recording()
    row = value["measurements"][0]
    if corruption == "epoch":
        row["epoch"] = 4
    elif corruption == "counter":
        value["drained"]["popped"] = 1
    elif corruption == "support_count":
        value["supported_count"] = 2
    elif corruption == "phase":
        row["phase_step_q32"] += 1
    elif corruption == "start":
        row["native_start_sample"] = str(int(row["native_start_sample"]) + 1)
    elif corruption == "frame":
        value["measurements"][1]["frame"] = 0
    elif corruption == "tag":
        row["tag"] = 10
    elif corruption == "sequence":
        row["sequence"] = 1
    elif corruption == "fault":
        row["hardware_fault"] = 1
    elif corruption == "count":
        row["sample_count"] = 1
    elif corruption == "overflow":
        row["reference_prefix_integral"][0] = str(2**68)
    elif corruption == "integer_number":
        row["native_start_sample"] = int(row["native_start_sample"])
    elif corruption == "unknown":
        value["unexpected"] = 0
    elif corruption == "qualified":
        value["physical_precision_qualified"] = True
    elif corruption == "nonfinite":
        row["cfo_hz"] = float("nan")
    elif corruption == "descriptor_expiry":
        value["descriptors"][0]["expires_sample"] = "1"
    elif corruption == "repeat":
        row["repeat"] = 2
    elif corruption == "boolean_counter":
        row["sequence"] = False
    elif corruption == "uncleared":
        value["final"]["status"] = 51
    elif corruption == "unowned_configured":
        value["drained"].update(configured=3, cancelled=1)
    with pytest.raises(ValueError):
        parse(value)


def test_cancelled_work_remains_accounted_without_invented_measurements():
    value = recording()
    value["drained"].update(configured=3, cancelled=1)
    descriptor = value["descriptors"][0]
    descriptor["repeats"] = 3
    descriptor["expires_sample"] = str(int(descriptor["expires_sample"]) + 80001)
    summary, rows = recording_review(parse(value))
    assert len(rows) == 2 and summary["drained"]["cancelled"] == 1


def test_empty_closed_recording_has_no_cfo_or_time_claim():
    value = recording()
    value.update(descriptors=[], measurements=[], head_count=0, supported_count=0, rejected_count=0)
    value["drained"] = copy.deepcopy(value["final"])
    summary, rows = recording_review(parse(value))
    assert not rows and summary["native_sample_anchor"] is None
    assert summary["supported_cfo_min_hz"] is None and summary["observed_start_span_s"] is None


def test_hash_mismatch_and_duplicate_json_create_no_output(tmp_path):
    source = tmp_path / "recording.json"
    raw = json.dumps(recording()).encode()
    source.write_bytes(raw)
    with pytest.raises(ValueError, match="expected bytes"):
        review_native_recording(source, tmp_path / "out", expected_sha256="0" * 64)
    assert not (tmp_path / "out").exists()
    raw = raw.replace(b'"epoch": 3', b'"epoch": 3, "epoch": 3', 1)
    source.write_bytes(raw)
    with pytest.raises(ValueError, match="duplicate"):
        load_native_recording(source, expected_sha256=hashlib.sha256(raw).hexdigest())


def test_cli_keeps_every_frame_and_never_overwrites_output(tmp_path):
    source = tmp_path / "recording.json"
    source.write_text(json.dumps(recording()))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    output = tmp_path / "review"
    command = [
        sys.executable,
        "-m",
        "leo.cli.native_journal_recording",
        "--recording",
        str(source),
        "--sha256",
        digest,
        "--output",
        str(output),
    ]
    run = subprocess.run(command, capture_output=True, text=True, check=True)
    summary = json.loads(run.stdout)
    assert summary["recording_export_sha256"] == digest
    with (output / "measurements.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2 and rows[1]["supported"] == "False"
    assert rows[0]["native_start_sample"] == str(2**60 + 1)
    before = (output / "summary.json").read_bytes()
    again = subprocess.run(command, capture_output=True, text=True)
    assert again.returncode != 0 and (output / "summary.json").read_bytes() == before


def binding_for(value, export_digest):
    start = int(value["measurements"][0]["native_start_sample"])
    origin = start - start % 24 - 1272
    return dict(
        schema="starlink-glrt-native-source-binding/v1",
        evidence_mode="retrospective_retained_owner_correspondence",
        recording_export_sha256=export_digest,
        journal_sha256=value["journal_sha256"],
        owner_receipt_sha256="b" * 64,
        collector_protocol_sha256="c" * 64,
        collector_summary_sha256="d" * 64,
        collector_final_snapshot_sha256="e" * 64,
        coarse_iq_sha256="f" * 64,
        coarse_iq_bytes=400000,
        serial="test-radio",
        host="192.168.1.14",
        boot_id="336a3c4c-8ab3-4758-ae9e-6967808e2a6d",
        firmware="test-native",
        fit_sha256="a" * 64,
        visit=1105016,
        epoch=3,
        episode_index=0,
        source_rate_hz=60000000,
        output_rate_hz=2500000,
        output_samples=100000,
        native_origin=str(origin),
        native_last_output_center=str(origin + 24 * 99999),
        native_samples_per_output_sample=24,
        native_group_delay_samples=1272,
        runtime_result=-5,
        owner_status="failed",
        head_count=2,
        supported_count=1,
        source_correspondence_verified=True,
        radio_signed_attestation=False,
        acquisition_verified=False,
        original_native_iq_verified=False,
        physical_precision_qualified=False,
    )


def test_bound_cli_preserves_failure_and_exact_coarse_time_axis(tmp_path):
    value = recording()
    source = tmp_path / "recording.json"
    source.write_text(json.dumps(value))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    binding = binding_for(value, digest)
    bound = tmp_path / "binding.json"
    bound.write_text(json.dumps(binding))
    bound_digest = hashlib.sha256(bound.read_bytes()).hexdigest()
    output = tmp_path / "review"
    command = [
        sys.executable,
        "-m",
        "leo.cli.native_journal_recording",
        "--recording",
        str(source),
        "--sha256",
        digest,
        "--source-binding",
        str(bound),
        "--source-binding-sha256",
        bound_digest,
        "--output",
        str(output),
    ]
    result = subprocess.run(command, check=True, capture_output=True, text=True)
    summary = json.loads(result.stdout)
    assert summary["schema"] == "native-journal-bound-application-review/v1"
    assert summary["radio_boot_source_bound"] and summary["runtime_result"] == -5
    assert summary["owner_status"] == "failed" and not summary["acquisition_verified"]
    assert summary["source_binding"] == binding
    assert summary["source_binding_sha256"] == bound_digest
    with (output / "measurements.csv").open() as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 2 and rows[1]["supported"] == "False"
    expected = (
        int(value["measurements"][0]["native_start_sample"]) - int(binding["native_origin"])
    ) / 60000000
    assert float(rows[0]["coarse_relative_scheduled_start_s"]) == expected
    assert float(rows[0]["coarse_relative_refined_start_s"]) == expected - 8e-9
    assert float(rows[0]["coarse_relative_pilot_center_s"]) == expected + 79199 / 120000000


@pytest.mark.parametrize(
    "corruption",
    [
        "export",
        "journal",
        "epoch",
        "count",
        "origin",
        "bytes",
        "boot",
        "excluded",
        "host",
        "signed",
        "outside",
        "unknown",
    ],
)
def test_wrong_source_binding_cannot_qualify_a_recording(corruption):
    value = recording()
    model = parse(value)
    binding = binding_for(value, "a" * 64)
    if corruption == "export":
        binding["recording_export_sha256"] = "b" * 64
    elif corruption == "journal":
        binding["journal_sha256"] = "b" * 64
    elif corruption == "epoch":
        binding["epoch"] = 4
    elif corruption == "count":
        binding["head_count"] = 3
    elif corruption == "origin":
        binding["native_origin"] = str(2**64)
    elif corruption == "bytes":
        binding["coarse_iq_bytes"] -= 4
    elif corruption == "boot":
        binding["boot_id"] = "not-a-boot"
    elif corruption == "excluded":
        binding["serial"] = "1040007c4a94000211000b009186843ef2"
    elif corruption == "host":
        binding["host"] = "127.0.0.1"
    elif corruption == "signed":
        binding["radio_signed_attestation"] = True
    elif corruption == "outside":
        for key in ("native_origin", "native_last_output_center"):
            binding[key] = str(int(binding[key]) + 2400000)
    elif corruption == "unknown":
        binding["unexpected"] = 1
    with pytest.raises(ValueError):
        NativeJournalSourceBindingV1.model_validate_json(json.dumps(binding)).require_recording(
            model, export_sha256="a" * 64
        )


def test_binding_flags_and_digest_are_required_before_output(tmp_path):
    source = tmp_path / "recording.json"
    source.write_text(json.dumps(recording()))
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    binding = tmp_path / "binding.json"
    binding.write_text(json.dumps(binding_for(recording(), digest)))
    output = tmp_path / "review"
    with pytest.raises(ValueError, match="required together"):
        review_native_recording(source, output, expected_sha256=digest, source_binding=binding)
    with pytest.raises(ValueError, match="expected bytes"):
        review_native_recording(
            source,
            output,
            expected_sha256=digest,
            source_binding=binding,
            expected_binding_sha256="0" * 64,
        )
    assert not output.exists()
