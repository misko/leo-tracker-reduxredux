from leo.cli.scan_position_methods import evaluated_result, reference_error_m
from leo.contracts.position_methods import ReferencePositionV1


def test_completion_verifies_artifacts_and_capture_authority(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from leo.cli import scan_position_methods as subject
    from leo.contracts.digests import canonical_digest

    reads = []
    document = SimpleNamespace(
        configuration_sha256=canonical_digest(subject.configuration()),
        input_manifest_sha256="capture-a",
    )
    manifest = SimpleNamespace(
        document=document, artifacts=[SimpleNamespace(method="expanded-doppler")]
    )
    store = SimpleNamespace(
        status=lambda _: SimpleNamespace(manifest=manifest),
        artifact=lambda *args: reads.append(args) or b"verified",
    )
    monkeypatch.setattr(subject, "PositionMethodsStore", lambda _: store)
    assert not subject.position_methods_complete(
        tmp_path, "scan", expected_input_manifest_sha256="capture-b"
    )
    assert not reads
    assert subject.position_methods_complete(
        tmp_path, "scan", expected_input_manifest_sha256="capture-a"
    )
    assert reads == [("scan", "expanded-doppler")]


def test_reference_evaluation_changes_error_not_estimate():
    fit = dict(
        state="complete",
        latitude_deg=37.8,
        longitude_deg=-122.4,
        training_rms_hz=30.0,
        evaluation_rms_hz=35.0,
    )
    first = evaluated_result(
        "expanded-doppler",
        fit,
        reference=ReferencePositionV1(latitude_deg=37.8, longitude_deg=-122.4),
    )
    second = evaluated_result(
        "expanded-doppler",
        fit,
        reference=ReferencePositionV1(latitude_deg=38.0, longitude_deg=-122.0),
    )
    assert first.latitude_deg == second.latitude_deg == 37.8
    assert first.longitude_deg == second.longitude_deg == -122.4
    assert first.diagnostics == second.diagnostics
    assert first.horizontal_error_m == 0
    assert second.horizontal_error_m > 10_000
    assert fit["state"] == "complete"


def test_full_configuration_is_finite_json_diagnostic():
    from leo.cli.scan_position_methods import configuration

    result = evaluated_result(
        "expanded-doppler",
        {
            "state": "insufficient",
            "reasons": ["no-tracks"],
            "configuration": configuration(),
        },
    )
    assert result.diagnostics["configuration"]["formal_orbit"]["sigma_bounds_hz"] == [5.0, 2000.0]


def test_failed_fit_never_reports_coordinate_or_reference_error():
    result = evaluated_result(
        "orbit-corrected",
        dict(
            state="failed", latitude_deg=37.0, longitude_deg=-122.0, reasons=["exact-check-failed"]
        ),
    )
    assert result.latitude_deg is None
    assert result.longitude_deg is None
    assert result.horizontal_error_m is None


def test_horizontal_error_handles_dateline():
    reference = ReferencePositionV1(latitude_deg=0, longitude_deg=179.99)
    assert 2_000 < reference_error_m(0, -179.99, reference) < 2_300
