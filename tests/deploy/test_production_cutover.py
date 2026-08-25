from __future__ import annotations

import copy
import hashlib
import json
import runpy
import socket
import subprocess
import time
import tomllib
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).parents[2]
SCRIPT = PROJECT_ROOT / "deploy" / "scripts" / "verify-production-cutover"
SCRIPT_GLOBALS = runpy.run_path(str(SCRIPT))


def _call(name: str, *args: object, **kwargs: object) -> Any:
    function = SCRIPT_GLOBALS[name]
    return function(*args, **kwargs)


def _write(path: Path, payload: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _stage_reviewed_profiles(release: Path) -> None:
    for relative in SCRIPT_GLOBALS["REVIEWED_CAPTURE_PROFILE_SHA256"]:
        source = PROJECT_ROOT / relative
        target = release / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())


def _canonical_target_digest(target: dict[str, Any]) -> str:
    payload = json.dumps(
        target,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _lossless_metrics(radio_id: str, sample_count: int) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "radio_id": radio_id,
        "requested_sample_count": sample_count,
        "observed_sample_count": sample_count,
        "device_span_sample_count": sample_count,
        "observed_gap_count": 0,
        "observed_missing_sample_count": 0,
        "observed_overflow_count": 0,
        "enqueue_failure_count": 0,
    }


def _usb_control_radios() -> list[dict[str, Any]]:
    return [
        {
            "schema_version": 2,
            "radio_id": "usb_control_pluto_003a",
            "serial": "104000bac4950008230026001b440a003a",
            "uri": "usb:5.27.5",
            "transport": "iio_usb",
            "model": "Pluto+",
            "firmware_version": "v0.41-control-a",
            "hardware_revision": None,
        },
        {
            "schema_version": 2,
            "radio_id": "usb_control_pluto_3ef2",
            "serial": "1040007c4a94000211000b009186843ef2",
            "uri": "usb:3.21.5",
            "transport": "iio_usb",
            "model": "Pluto+",
            "firmware_version": "v0.41-control-b",
            "hardware_revision": None,
        },
    ]


def _strict_rate_prerequisites() -> dict[str, Any]:
    radio_ids = ("radio_pluto_5d4d", "radio_pluto_19f2")
    safety = [
        {
            "schema_version": 1,
            "radio_id": radio_id,
            "pre_safety_evidence_sha256": "sha256:" + f"{index + 1:x}" * 64,
            "post_safety_evidence_sha256": "sha256:" + f"{index + 3:x}" * 64,
            "pre_tx_safe": True,
            "post_tx_safe": True,
            "rx_settings_restored": True,
            "passed": True,
        }
        for index, radio_id in enumerate(radio_ids)
    ]
    canaries = [
        {
            "schema_version": 1,
            "transport": "iio_ip",
            "duration_ns": 1_000_000_000,
            "sample_rate_hz": 3_000_000,
            "bandwidth_hz": 2_500_000,
            "evidence_sha256": "sha256:" + f"{index + 5:x}" * 64,
            "metrics": _lossless_metrics(radio_id, 3_000_000),
            "passed": True,
        }
        for index, radio_id in enumerate(radio_ids)
    ]
    usb_radios = _usb_control_radios()
    usb_intervals = [
        {
            "schema_version": 2,
            "radio_id": radio["radio_id"],
            "started_monotonic_ns": 1_000_000_000,
            "ended_monotonic_ns": 61_000_000_000,
        }
        for radio in usb_radios
    ]
    usb_restoration = [
        {
            "schema_version": 2,
            "radio_id": radio["radio_id"],
            "pre_settings_evidence_sha256": "sha256:" + f"{index + 9:x}" * 64,
            "post_settings_evidence_sha256": "sha256:" + f"{index + 11:x}" * 64,
            "rx_settings_restored": True,
            "passed": True,
        }
        for index, radio in enumerate(usb_radios)
    ]
    return {
        "schema_version": 2,
        "radio_safety": safety,
        "native_ip_canaries": canaries,
        "usb_control_arm": {
            "schema_version": 2,
            "transport": "iio_usb",
            "simultaneous": True,
            "duration_ns": 60_000_000_000,
            "sample_rate_hz": 3_000_000,
            "bandwidth_hz": 2_500_000,
            "evidence_sha256": "sha256:" + "7" * 64,
            "minimum_overlap_fraction": 0.99,
            "radios": usb_radios,
            "capture_intervals": usb_intervals,
            "radio_restoration": usb_restoration,
            "radio_metrics": [
                _lossless_metrics(radio["radio_id"], 180_000_000) for radio in usb_radios
            ],
            "passed": True,
        },
        "writer_benchmark": {
            "schema_version": 1,
            "payload_kind": "incompressible",
            "evidence_sha256": "sha256:" + "8" * 64,
            "uncompressed_bytes_written": 144_000_000,
            "elapsed_ns": 2_000_000_000,
            "sustained_bytes_per_second": 72_000_000,
            "passed": True,
        },
    }


def _expected_rate_radios() -> list[dict[str, Any]]:
    return [
        {
            "radio_id": "radio_pluto_5d4d",
            "serial": "1040005e0b100007100010000bf33a5d4d",
            "uri": "ip:192.168.1.20",
            "transport": "iio_ip",
            "firmware_version": "v0.38",
        },
        {
            "radio_id": "radio_pluto_19f2",
            "serial": "10400056f695001322002d0010ad1719f2",
            "uri": "ip:192.168.1.21",
            "transport": "iio_ip",
            "firmware_version": "v0.38",
        },
    ]


def _live_station_probe_payload() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "radios": [
            {
                "schema_version": 1,
                **radio,
                "metadata_abi_version": 1,
                "supports_device_sample_counter": True,
                "supports_continuity_sequence": True,
            }
            for radio in _expected_rate_radios()
        ],
    }


def test_qnap_is_rejected_lexically_without_access() -> None:
    with pytest.raises(ValueError, match="must not resolve beneath /mnt/qnap01"):
        _call("reject_qnap", Path("/mnt/qnap01/never-open-this"), "evidence")


@pytest.mark.parametrize(
    ("reviewed", "tampered"),
    (
        ("continuity_policy: allow_segments", "continuity_policy: require_contiguous"),
        (
            "tags: [CAPTURE_ONLY, EXPERIMENTAL, LIVE, RANDOM_TUNING]",
            "tags: [EXPERIMENTAL, LIVE, RANDOM_TUNING]",
        ),
    ),
)
def test_staged_profile_bytes_reject_five_msps_policy_or_tag_tamper(
    tmp_path: Path,
    reviewed: str,
    tampered: str,
) -> None:
    release = tmp_path / "release"
    _stage_reviewed_profiles(release)
    _call("verify_staged_capture_profiles", release)

    five_msps = release / "profiles/starlink-ch4-lower-5m-60s-segmented-v2.yaml"
    payload = five_msps.read_text(encoding="utf-8")
    assert reviewed in payload
    five_msps.write_text(payload.replace(reviewed, tampered), encoding="utf-8")

    with pytest.raises(ValueError, match=r"digest mismatch: .*5m-60s-segmented"):
        _call("verify_staged_capture_profiles", release)


def test_staged_acquisition_service_requires_exact_profile_and_radio_order(
    tmp_path: Path,
) -> None:
    _call("verify_staged_acquisition_service", PROJECT_ROOT)

    release = tmp_path / "release"
    service = release / SCRIPT_GLOBALS["ACQUISITION_SERVICE_RELATIVE_PATH"]
    service.parent.mkdir(parents=True)
    expected = SCRIPT_GLOBALS["EXPECTED_ACQUISITION_EXEC_START"]
    service.write_text(f"[Service]\nExecStart={expected}\n", encoding="utf-8")
    _call("verify_staged_acquisition_service", release)

    profile_3m = "--profile ${LEO_CAPTURE_PROFILE_3M} "
    profile_5m = "--profile ${LEO_CAPTURE_PROFILE_5M} "
    radio_a = "--radio radio_pluto_5d4d "
    radio_b = "--radio radio_pluto_19f2 "
    tampered_commands = (
        expected.replace(profile_3m + profile_5m, profile_5m + profile_3m),
        expected.replace(profile_5m, ""),
        expected.replace(profile_5m, profile_5m + profile_5m),
        expected.replace(radio_a + radio_b, radio_b + radio_a),
        expected.replace(radio_b, ""),
        expected.replace(radio_b, radio_b + "--radio unexpected-radio "),
    )
    assert len(set(tampered_commands)) == len(tampered_commands)
    for command in tampered_commands:
        service.write_text(f"[Service]\nExecStart={command}\n", encoding="utf-8")
        with pytest.raises(ValueError, match="exact ordered profile and radio pool"):
            _call("verify_staged_acquisition_service", release)


def test_live_station_probe_uses_staged_adapter_and_rejects_identity_drift(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    release = tmp_path / "release"
    payload = _live_station_probe_payload()
    calls: list[tuple[tuple[str, ...], float | None]] = []

    def fake_command(*argv: str, timeout_seconds: float | None = None) -> str:
        calls.append((argv, timeout_seconds))
        return json.dumps(payload)

    function = SCRIPT_GLOBALS["probe_live_station_radios"]
    monkeypatch.setitem(function.__globals__, "command", fake_command)
    assert (
        _call(
            "probe_live_station_radios",
            release,
            expected_radios=_expected_rate_radios(),
        )
        == payload
    )
    argv, timeout_seconds = calls[-1]
    assert argv[:4] == ("runuser", "-u", "leo", "--")
    assert argv[4:7] == (str(release / ".venv/bin/python"), "-I", "-c")
    assert "from leo.radio import PlutoIioRadioSource" in argv[7]
    assert timeout_seconds == 30.0

    payload = _live_station_probe_payload()
    payload["radios"][0]["firmware_version"] = "v0.39"
    with pytest.raises(ValueError, match="firmware differs"):
        _call(
            "probe_live_station_radios",
            release,
            expected_radios=_expected_rate_radios(),
        )

    payload = _live_station_probe_payload()
    payload["radios"][1]["serial"] = "different-serial"
    with pytest.raises(ValueError, match="identity differs"):
        _call(
            "probe_live_station_radios",
            release,
            expected_radios=_expected_rate_radios(),
        )

    payload = _live_station_probe_payload()
    payload["radios"][0]["metadata_abi_version"] = 2
    with pytest.raises(ValueError, match="metadata ABI"):
        _call(
            "probe_live_station_radios",
            release,
            expected_radios=_expected_rate_radios(),
        )

    payload = _live_station_probe_payload()
    payload["radios"][0]["supports_device_sample_counter"] = False
    with pytest.raises(ValueError, match="counter-authoritative capabilities"):
        _call(
            "probe_live_station_radios",
            release,
            expected_radios=_expected_rate_radios(),
        )


def test_live_station_probe_runs_only_after_both_unit_scopes_are_quiescent() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    verify_source = text[text.index("def verify(args:") : text.index("\ndef main()")]
    probe = verify_source.index("    probe_live_station_radios(")
    assert verify_source.index("    if unexpected_legacy:") < probe
    assert verify_source.index("    if system_active:") < probe


def test_environment_binds_exact_release_roots_and_station_radios() -> None:
    revision = "a" * 40
    radios = [
        {
            "radio_id": "radio_pluto_5d4d",
            "serial": "1040005e0b100007100010000bf33a5d4d",
            "host": "192.168.1.20",
            "receiver_count": 2,
        },
        {
            "radio_id": "radio_pluto_19f2",
            "serial": "10400056f695001322002d0010ad1719f2",
            "host": "192.168.1.21",
            "receiver_count": 2,
        },
    ]
    environment = "\n".join(
        (
            "LEO_BULK_ROOT=/srv/bulk/leo",
            "LEO_QUALIFICATION_ROOT=/srv/bulk/leo/qualification",
            "LEO_CAPTURE_EVIDENCE_ROOT=/srv/bulk/leo/qualification/capture",
            "LEO_LEGACY_EVIDENCE_ROOT=/srv/bulk/leo/qualification/legacy",
            "LEO_STATION_AUTHORITY_ROOT=/etc/leo/station-authority",
            "LEO_STATION_TOPOLOGY_RELATIVE_PATH=gauss-four-path-postreboot-20260816-v1.json",
            "LEO_STATION_TOPOLOGY_FILE_DIGEST="
            "sha256:5ec14f15bfe2a6abc52024f41db29b4ab6123209e6c4779a47644b1e70c477ae",
            "LEO_FIXTURE_PATH_AUTHORITIES_JSON=[]",
            "LEO_CAPTURE_PROFILE=starlink-ch4-lower-2p5m-60s-continuity-v2",
            "LEO_CAPTURE_PROFILE_3M=starlink-ch4-lower-3m-60s-capture-v2",
            "LEO_CAPTURE_PROFILE_5M=starlink-ch4-lower-5m-60s-segmented-v2",
            "LEO_CAPTURE_INTERVAL_SECONDS=180",
            "LEO_QUALIFICATION_PROFILE=starlink-ch4-lower-2p5m-60s-rx1-centered-continuity-v2",
            "LEO_SOAK_PROFILE=starlink-ch4-lower-2p5m-60s-continuity-v2",
            "LEO_SCANNER_ENABLED=true",
            "LEO_SCANNER_RADIO_ID=radio_pluto_5d4d",
            "LEO_SCANNER_INTERVAL_SECONDS=180",
            "LEO_SCANNER_MAXIMUM_LATENESS_SECONDS=180",
            "LEO_SCANNER_DWELL_MS=120",
            "LEO_SCANNER_GAIN_DB=40.0",
            "LEO_SCANNER_MARGIN_GATE=0.025",
            "LEO_SCANNER_REPORT_ROOT=/srv/bulk/leo/scanner-reports",
            f"LEO_PIPELINE_RELEASE_ID={revision}",
            f"LEO_RADIOS_JSON='{json.dumps(radios, separators=(',', ':'))}'",
        )
    )

    _call("verify_environment_text", environment, revision)

    with pytest.raises(ValueError, match="pipeline release ID"):
        _call("verify_environment_text", environment.replace(revision, "b" * 40), revision)
    with pytest.raises(ValueError, match="station topology"):
        _call(
            "verify_environment_text",
            environment.replace("radio_pluto_19f2", "pluto-b"),
            revision,
        )
    with pytest.raises(ValueError, match="station topology"):
        _call(
            "verify_environment_text",
            environment.replace(
                json.dumps(radios, separators=(",", ":")),
                json.dumps(list(reversed(radios)), separators=(",", ":")),
            ),
            revision,
        )
    with pytest.raises(ValueError, match="capture interval"):
        _call(
            "verify_environment_text",
            environment.replace(
                "LEO_CAPTURE_INTERVAL_SECONDS=180", "LEO_CAPTURE_INTERVAL_SECONDS=0"
            ),
            revision,
        )
    with pytest.raises(ValueError, match="dual-RX"):
        _call(
            "verify_environment_text",
            environment.replace(
                "LEO_CAPTURE_PROFILE=starlink-ch4-lower-2p5m-60s-continuity-v2",
                "LEO_CAPTURE_PROFILE=starlink-ch4-lower-2p5m-60s-rx1-centered-v1",
            ),
            revision,
        )
    with pytest.raises(ValueError, match="sample-rate profile pool"):
        _call(
            "verify_environment_text",
            environment.replace(
                "LEO_CAPTURE_PROFILE_5M=starlink-ch4-lower-5m-60s-segmented-v2",
                "LEO_CAPTURE_PROFILE_5M=starlink-ch4-lower-5m-60s-capture-v2",
            ),
            revision,
        )
    with pytest.raises(ValueError, match="qualification and soak"):
        _call(
            "verify_environment_text",
            environment.replace(
                "starlink-ch4-lower-2p5m-60s-rx1-centered-continuity-v2",
                "starlink-ch4-lower-2p5m-60s-rx1-centered-v1",
            ),
            revision,
        )
    with pytest.raises(ValueError, match="scanner configuration"):
        _call(
            "verify_environment_text",
            environment.replace("LEO_SCANNER_ENABLED=true", "LEO_SCANNER_ENABLED=false"),
            revision,
        )
    station_lines = tuple(
        line for line in environment.splitlines() if line.startswith("LEO_STATION_")
    )
    for line in station_lines:
        with pytest.raises(ValueError, match="exact reviewed root"):
            _call("verify_environment_text", environment.replace(f"{line}\n", ""), revision)
    with pytest.raises(ValueError, match="exact reviewed root"):
        _call(
            "verify_environment_text",
            environment.replace("/etc/leo/station-authority", "/tmp/retargeted"),
            revision,
        )
    with pytest.raises(ValueError, match="exact reviewed root"):
        _call(
            "verify_environment_text",
            environment.replace(
                "LEO_FIXTURE_PATH_AUTHORITIES_JSON=[]",
                "LEO_FIXTURE_PATH_AUTHORITIES_JSON={}",
            ),
            revision,
        )
    with pytest.raises(ValueError, match="exact reviewed root"):
        _call(
            "verify_environment_text",
            environment.replace("LEO_FIXTURE_PATH_AUTHORITIES_JSON=[]\n", ""),
            revision,
        )


def test_installed_station_authority_requires_exact_inode_and_digest(tmp_path: Path) -> None:
    parent = tmp_path / "leo"
    root = parent / "station-authority"
    parent.mkdir(mode=0o750)
    root.mkdir(mode=0o750)
    source = PROJECT_ROOT / "deploy/station/gauss-four-path-postreboot-20260816-v1.json"
    installed = root / source.name
    installed.write_bytes(source.read_bytes())
    installed.chmod(0o440)

    _call(
        "verify_station_authority_install",
        installed,
        expected_uid=installed.stat().st_uid,
        expected_gid=installed.stat().st_gid,
    )
    with pytest.raises(ValueError, match="ownership"):
        _call(
            "verify_station_authority_install",
            installed,
            expected_uid=installed.stat().st_uid,
            expected_gid=installed.stat().st_gid + 1,
        )

    installed.chmod(0o640)
    with pytest.raises(ValueError, match="sealed"):
        _call(
            "verify_station_authority_install",
            installed,
            expected_uid=installed.stat().st_uid,
            expected_gid=installed.stat().st_gid,
        )
    installed.write_bytes(b"{}")
    installed.chmod(0o440)
    with pytest.raises(ValueError, match="digest mismatch"):
        _call(
            "verify_station_authority_install",
            installed,
            expected_uid=installed.stat().st_uid,
            expected_gid=installed.stat().st_gid,
        )


def test_scanner_data_directories_must_be_installed_exactly(tmp_path: Path) -> None:
    root = tmp_path / "bulk"
    root.mkdir()
    for relative in ("scanner-recordings", "scanner-reports"):
        path = root / relative
        path.mkdir(mode=0o770)
        path.chmod(0o2770)

    uid = root.stat().st_uid
    gid = root.stat().st_gid
    _call("verify_scanner_data_directories", root, expected_uid=uid, expected_gid=gid)

    (root / "scanner-reports").chmod(0o770)
    with pytest.raises(ValueError, match="permissions are not exact"):
        _call("verify_scanner_data_directories", root, expected_uid=uid, expected_gid=gid)

    (root / "scanner-reports").rmdir()
    with pytest.raises(ValueError, match="is missing"):
        _call("verify_scanner_data_directories", root, expected_uid=uid, expected_gid=gid)


def test_standard_cutover_receipt_is_exact_and_bound_to_staged_golden(
    tmp_path: Path,
) -> None:
    receipt_relative = Path("corpus/goldens/trial-132-standard-v2-full-review-receipt.json")
    summary_relative = Path("corpus/goldens/trial-132-standard-v2-summary.json")
    release = tmp_path / "release"
    receipt_source = PROJECT_ROOT / receipt_relative
    summary_source = PROJECT_ROOT / summary_relative
    (release / receipt_relative).parent.mkdir(parents=True)
    (release / receipt_relative).write_bytes(receipt_source.read_bytes())
    (release / summary_relative).write_bytes(summary_source.read_bytes())
    sealed = tmp_path / "standard-regression-receipt.json"
    sealed.write_bytes(receipt_source.read_bytes())
    sealed.chmod(0o440)
    receipt = _call("load_json", sealed, "Standard four-path regression receipt")

    _call("verify_standard_regression_receipt", sealed, receipt, release=release)

    (release / summary_relative).write_text("{}\n")
    with pytest.raises(ValueError, match="reviewed Standard golden"):
        _call("verify_standard_regression_receipt", sealed, receipt, release=release)
    (release / summary_relative).write_bytes(summary_source.read_bytes())
    tampered = dict(receipt)
    tampered["fixture_id"] = "other"
    with pytest.raises(ValueError, match="receipt contents"):
        _call("verify_standard_regression_receipt", sealed, tampered, release=release)


def test_json_receipt_must_be_sealed_and_not_a_symlink(tmp_path: Path) -> None:
    receipt = tmp_path / "receipt.json"
    receipt.write_text('{"accepted": true}\n')
    with pytest.raises(ValueError, match="not sealed read-only"):
        _call("load_json", receipt, "receipt")

    receipt.chmod(0o440)
    assert _call("load_json", receipt, "receipt") == {"accepted": True}

    link = tmp_path / "receipt-link.json"
    link.symlink_to(receipt)
    with pytest.raises(ValueError, match="must not be a symlink"):
        _call("load_json", link, "receipt")


def test_three_msps_receipt_is_exact_ten_trial_station_authority(tmp_path: Path) -> None:
    revision = "a" * 40
    now_utc_ns = time.time_ns()
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)
    release = tmp_path / "release"
    _write(release / "pyproject.toml", (PROJECT_ROOT / "pyproject.toml").read_bytes())
    runtime = {
        "schema_version": 1,
        "metadata_abi": 1,
        "libiio_version": "0.25 / test",
        "native_libiio_sha256": "b" * 64,
        "pylibiio_sha256": "c" * 64,
    }
    _write(
        release / ".venv/share/pluto-plus-utils/metadata-runtime.json",
        json.dumps(runtime).encode("utf-8"),
    )
    ppu_revision = project["tool"]["uv"]["sources"]["pluto-plus-utils"]["rev"]
    receipt = {
        "kind": "contiguous_rate_qualification",
        "schema_version": 2,
        "created_utc_ns": now_utc_ns,
        "complete": True,
        "passed": True,
        "target": {
            "schema_version": 2,
            "qualification_id": f"native-ip-3m-{revision[:12]}",
            "profile_revision_digest": SCRIPT_GLOBALS["CONTIGUOUS_RATE_3M_PROFILE_DIGEST"],
            "capture_plan_digest": SCRIPT_GLOBALS["CONTIGUOUS_RATE_3M_PLAN_DIGEST"],
            "sample_rate_hz": 3_000_000,
            "bandwidth_hz": 2_500_000,
            "requested_sample_count": 180_000_000,
            "expected_radios": _expected_rate_radios(),
            "expected_host": {
                "hostname": socket.gethostname(),
                "machine_id": Path("/etc/machine-id").read_text().strip(),
                "operating_system": "test-linux",
            },
            "expected_producer": {
                "name": "leo-acquisition",
                "version": project["project"]["version"],
                "source_revision": revision,
            },
            "pluto_plus_utils_revision": ppu_revision,
            "libiio_version": "0.25 / test",
            "libiio_library_sha256": "sha256:" + "b" * 64,
            "python_iio_sha256": "sha256:" + "c" * 64,
            "native_network_interface": "enp132s0",
            "native_source_address": "192.168.1.142",
            "prerequisites": _strict_rate_prerequisites(),
            "policy": {
                "schema_version": 1,
                "required_trial_count": 10,
                "minimum_overlap_fraction": 0.99,
                "required_kernel_buffers": 8,
                "required_queue_capacity_refills": 32,
                "maximum_queue_high_water_fraction": 0.75,
                "required_metadata_abi_version": 1,
                "maximum_refill_service_interval_ns": 699_050_666,
                "required_tags": ["QUALIFICATION"],
            },
        },
        "checks": [
            {
                "trial_id": f"trial-{index:02d}",
                "session_id": f"session-{index:02d}",
                "manifest_sha256": "sha256:" + f"{index:064x}",
                "passed": True,
                "errors": [],
            }
            for index in range(10)
        ],
    }
    receipt["target_digest"] = _canonical_target_digest(receipt["target"])

    _call("verify_contiguous_rate_3m_receipt", receipt, revision=revision, release=release)

    v3_receipt = copy.deepcopy(receipt)
    v3_receipt["schema_version"] = 3
    v3_receipt["target"]["schema_version"] = 3
    v3_prerequisites = v3_receipt["target"]["prerequisites"]
    v3_prerequisites["schema_version"] = 3
    v3_prerequisites.pop("usb_control_arm")
    v3_receipt["target_digest"] = _canonical_target_digest(v3_receipt["target"])
    _call(
        "verify_contiguous_rate_3m_receipt_v3",
        v3_receipt,
        revision=revision,
        release=release,
    )

    v3_with_usb = copy.deepcopy(v3_receipt)
    v3_with_usb["target"]["prerequisites"]["usb_control_arm"] = copy.deepcopy(
        receipt["target"]["prerequisites"]["usb_control_arm"]
    )
    v3_with_usb["target_digest"] = _canonical_target_digest(v3_with_usb["target"])
    with pytest.raises(ValueError, match="prerequisites have an unsupported contract"):
        _call(
            "verify_contiguous_rate_3m_receipt_v3",
            v3_with_usb,
            revision=revision,
            release=release,
        )

    for required_prerequisite in (
        "radio_safety",
        "native_ip_canaries",
        "writer_benchmark",
    ):
        incomplete_v3 = copy.deepcopy(v3_receipt)
        incomplete_v3["target"]["prerequisites"].pop(required_prerequisite)
        incomplete_v3["target_digest"] = _canonical_target_digest(incomplete_v3["target"])
        with pytest.raises(ValueError, match="prerequisites have an unsupported contract"):
            _call(
                "verify_contiguous_rate_3m_receipt_v3",
                incomplete_v3,
                revision=revision,
                release=release,
            )

    with pytest.raises(ValueError, match="not a complete strict pass"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            v3_receipt,
            revision=revision,
            release=release,
        )
    with pytest.raises(ValueError, match="not a complete strict pass"):
        _call(
            "verify_contiguous_rate_3m_receipt_v3",
            receipt,
            revision=revision,
            release=release,
        )

    unsafe_v3 = copy.deepcopy(v3_receipt)
    unsafe_v3["target"]["prerequisites"]["radio_safety"][0]["post_tx_safe"] = False
    unsafe_v3["target_digest"] = _canonical_target_digest(unsafe_v3["target"])
    with pytest.raises(ValueError, match="radio safety prerequisites"):
        _call(
            "verify_contiguous_rate_3m_receipt_v3",
            unsafe_v3,
            revision=revision,
            release=release,
        )

    lossy_canary_v3 = copy.deepcopy(v3_receipt)
    lossy_canary_v3["target"]["prerequisites"]["native_ip_canaries"][1]["metrics"][
        "observed_gap_count"
    ] = 1
    lossy_canary_v3["target_digest"] = _canonical_target_digest(lossy_canary_v3["target"])
    with pytest.raises(ValueError, match="native-IP canaries"):
        _call(
            "verify_contiguous_rate_3m_receipt_v3",
            lossy_canary_v3,
            revision=revision,
            release=release,
        )

    slow_writer_v3 = copy.deepcopy(v3_receipt)
    v3_writer = slow_writer_v3["target"]["prerequisites"]["writer_benchmark"]
    v3_writer["uncompressed_bytes_written"] = 71_999_999
    v3_writer["elapsed_ns"] = 1_000_000_000
    v3_writer["sustained_bytes_per_second"] = 71_999_999
    slow_writer_v3["target_digest"] = _canonical_target_digest(slow_writer_v3["target"])
    with pytest.raises(ValueError, match="writer prerequisite"):
        _call(
            "verify_contiguous_rate_3m_receipt_v3",
            slow_writer_v3,
            revision=revision,
            release=release,
        )

    missing_time = copy.deepcopy(receipt)
    missing_time.pop("created_utc_ns")
    with pytest.raises(ValueError, match="missing or not an actual integer"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            missing_time,
            revision=revision,
            release=release,
        )

    future = copy.deepcopy(receipt)
    future["created_utc_ns"] = now_utc_ns + 10 * 60 * 1_000_000_000
    with pytest.raises(ValueError, match="more than five minutes in the future"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            future,
            revision=revision,
            release=release,
        )

    stale = copy.deepcopy(receipt)
    stale["created_utc_ns"] = now_utc_ns - 25 * 60 * 60 * 1_000_000_000
    with pytest.raises(ValueError, match="older than 24 hours"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            stale,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["radio_safety"][0]["pre_safety_evidence_sha256"] = (
        "sha256:" + "9" * 64
    )
    with pytest.raises(ValueError, match="target digest does not bind the full target"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["radio_safety"][0]["pre_safety_evidence_sha256"] = (
        "not-a-digest"
    )
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="radio safety prerequisites"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["radio_safety"][1]["rx_settings_restored"] = False
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="radio safety prerequisites"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["native_ip_canaries"][0]["metrics"][
        "observed_sample_count"
    ] -= 1
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="native-IP canaries"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["usb_control_arm"]["simultaneous"] = False
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="USB control arm"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["usb_control_arm"]["radio_metrics"].reverse()
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="USB control arm"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["usb_control_arm"]["radios"][0]["serial"] = (
        "WRONG-CONTROL-SERIAL"
    )
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="USB control arm"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["usb_control_arm"]["radios"].reverse()
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="USB control arm"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["usb_control_arm"]["capture_intervals"][1][
        "started_monotonic_ns"
    ] = 2_000_000_001
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="USB control arm"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["usb_control_arm"]["radio_restoration"][0][
        "rx_settings_restored"
    ] = False
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="USB control arm"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    tampered["target"]["prerequisites"]["writer_benchmark"]["sustained_bytes_per_second"] += 1
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="writer prerequisite"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    tampered = copy.deepcopy(receipt)
    writer = tampered["target"]["prerequisites"]["writer_benchmark"]
    writer["uncompressed_bytes_written"] = 71_999_999
    writer["elapsed_ns"] = 1_000_000_000
    writer["sustained_bytes_per_second"] = 71_999_999
    tampered["target_digest"] = _canonical_target_digest(tampered["target"])
    with pytest.raises(ValueError, match="writer prerequisite"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            tampered,
            revision=revision,
            release=release,
        )

    receipt["target"]["expected_radios"].reverse()
    with pytest.raises(ValueError, match="radio identities"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            receipt,
            revision=revision,
            release=release,
        )
    receipt["target"]["expected_radios"].reverse()
    original_trial_id = receipt["checks"][4]["trial_id"]
    receipt["checks"][4]["trial_id"] = receipt["checks"][3]["trial_id"]
    with pytest.raises(ValueError, match="trial IDs are not independently unique"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            receipt,
            revision=revision,
            release=release,
        )
    receipt["checks"][4]["trial_id"] = original_trial_id

    original_session_id = receipt["checks"][4]["session_id"]
    receipt["checks"][4]["session_id"] = receipt["checks"][3]["session_id"]
    with pytest.raises(ValueError, match="session IDs are not independently unique"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            receipt,
            revision=revision,
            release=release,
        )
    receipt["checks"][4]["session_id"] = original_session_id

    original_manifest_digest = receipt["checks"][4]["manifest_sha256"]
    receipt["checks"][4]["manifest_sha256"] = receipt["checks"][3]["manifest_sha256"]
    with pytest.raises(ValueError, match="manifest digests are not independently unique"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            receipt,
            revision=revision,
            release=release,
        )
    receipt["checks"][4]["manifest_sha256"] = original_manifest_digest

    receipt["checks"][4]["passed"] = False
    with pytest.raises(ValueError, match="failed or malformed"):
        _call(
            "verify_contiguous_rate_3m_receipt",
            receipt,
            revision=revision,
            release=release,
        )


def test_release_inventory_and_lockfiles_verify_then_fail_on_tamper(tmp_path: Path) -> None:
    revision = "a" * 40
    release = tmp_path / "release"
    uv_digest = _write(release / "uv.lock", b"locked-python\n")
    npm_digest = _write(release / "web/package-lock.json", b"locked-node\n")
    run_root = tmp_path / "qualification" / "run-1"
    evidence_digest = _write(run_root / "logs/gate.log", b"passed\n")
    definition = {
        "source": {
            "git_revision": revision,
            "uv_lock_sha256": uv_digest,
            "package_lock_sha256": npm_digest,
        }
    }
    definition_bytes = json.dumps(definition, sort_keys=True).encode() + b"\n"
    definition_digest = _write(run_root / "definition.json", definition_bytes)
    receipt = {
        "definition_relative_path": "definition.json",
        "definition_sha256": definition_digest,
        "evidence": [
            {
                "relative_path": "logs/gate.log",
                "bytes": len(b"passed\n"),
                "sha256": evidence_digest,
            },
            {
                "relative_path": "definition.json",
                "bytes": len(definition_bytes),
                "sha256": definition_digest,
            },
        ],
    }
    receipt_path = run_root / "receipt.json"
    receipt_path.write_text(json.dumps(receipt))
    receipt_path.chmod(0o440)

    _call(
        "verify_release_evidence",
        receipt_path,
        receipt,
        release=release,
        revision=revision,
    )

    (run_root / "logs/gate.log").write_text("tampered\n")
    with pytest.raises(ValueError, match="resized|digest mismatch"):
        _call(
            "verify_release_evidence",
            receipt_path,
            receipt,
            release=release,
            revision=revision,
        )


def test_release_inventory_refuses_parent_traversal(tmp_path: Path) -> None:
    revision = "b" * 40
    release = tmp_path / "release"
    uv_digest = _write(release / "uv.lock", b"uv")
    npm_digest = _write(release / "web/package-lock.json", b"npm")
    run_root = tmp_path / "run"
    definition = {
        "source": {
            "git_revision": revision,
            "uv_lock_sha256": uv_digest,
            "package_lock_sha256": npm_digest,
        }
    }
    definition_bytes = json.dumps(definition).encode()
    definition_digest = _write(run_root / "definition.json", definition_bytes)
    receipt = {
        "definition_relative_path": "definition.json",
        "definition_sha256": definition_digest,
        "evidence": [{"relative_path": "../escape", "bytes": 0, "sha256": "0" * 64}],
    }
    receipt_path = run_root / "receipt.json"
    receipt_path.write_text("{}")
    receipt_path.chmod(0o440)

    with pytest.raises(ValueError, match="escapes its run"):
        _call(
            "verify_release_evidence",
            receipt_path,
            receipt,
            release=release,
            revision=revision,
        )


def test_lean_cutover_cli_accepts_standard_authority_without_soak() -> None:
    result = subprocess.run(
        (
            str(SCRIPT),
            "--revision",
            "not-a-revision",
            "--legacy-user",
            "mouse9911",
            "--release-receipt",
            "/does/not/exist",
            "--rate-qualification-receipt",
            "/does/not/exist",
            "--rate-qualification-receipt-sha256",
            "0" * 64,
            "--standard-regression-receipt",
            "/does/not/exist",
        ),
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "full lowercase 40-character SHA" in result.stderr
    assert "--soak-receipt" not in result.stderr


def test_cutover_allows_only_the_isolated_postgresql_user_unit() -> None:
    allowed = (
        "leo-forward-v2-postgresql.service loaded active running "
        "Isolated forward-only V2 PostgreSQL 16 database\n"
    )
    assert _call("unexpected_legacy_active_units", allowed) == ()

    output = allowed + (
        "leo-api-production.service loaded active running stale API\n"
        "leo-reconcile.timer loaded active waiting stale reconcile\n"
    )
    assert _call("unexpected_legacy_active_units", output) == (
        "leo-api-production.service loaded active running stale API",
        "leo-reconcile.timer loaded active waiting stale reconcile",
    )


def test_cutover_git_checks_are_read_only() -> None:
    text = SCRIPT.read_text()
    assert '("env", "GIT_OPTIONAL_LOCKS=0", "git", "-C", str(release))' in text
