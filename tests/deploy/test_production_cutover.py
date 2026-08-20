from __future__ import annotations

import hashlib
import json
import runpy
import subprocess
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


def test_qnap_is_rejected_lexically_without_access() -> None:
    with pytest.raises(ValueError, match="must not resolve beneath /mnt/qnap01"):
        _call("reject_qnap", Path("/mnt/qnap01/never-open-this"), "evidence")


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
            "LEO_CAPTURE_PROFILE=starlink-ch4-lower-2p5m-60s",
            "LEO_CAPTURE_INTERVAL_SECONDS=120",
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
            environment.replace("radio_pluto_5d4d", "pluto-a"),
            revision,
        )
    with pytest.raises(ValueError, match="capture interval"):
        _call(
            "verify_environment_text",
            environment.replace(
                "LEO_CAPTURE_INTERVAL_SECONDS=120", "LEO_CAPTURE_INTERVAL_SECONDS=0"
            ),
            revision,
        )
    with pytest.raises(ValueError, match="dual-RX"):
        _call(
            "verify_environment_text",
            environment.replace(
                "LEO_CAPTURE_PROFILE=starlink-ch4-lower-2p5m-60s",
                "LEO_CAPTURE_PROFILE=starlink-ch4-lower-2p5m-60s-rx1-centered-v1",
            ),
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
