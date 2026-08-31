"""Pure, versioned authority for release-qualification V2 evidence.

V1 documents remain historical persisted evidence.  V2 is additive and is the
first release-qualification contract whose exact command and result inventory
is suitable for production cutover authority.
"""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from typing import Any, Literal, cast

RELEASE_QUALIFICATION_V1_SCHEMA = "org.leo.release-qualification/v1"
RELEASE_QUALIFICATION_V2_SCHEMA = "org.leo.release-qualification/v2"
RELEASE_QUALIFICATION_V2_COMMAND_NAMES = (
    "protected-real-corpus",
    "standard-native-science",
    "standard-native-postgresql",
    "standard-native-real-corpus",
    "production-web-build",
    "production-chromium-e2e",
)
RELEASE_QUALIFICATION_V2_JUNIT_PATHS = {
    "protected-real-corpus": "results/real-corpus.junit.xml",
    "standard-native-science": "results/standard-native-science.junit.xml",
    "standard-native-postgresql": "results/standard-native-postgresql.junit.xml",
    "standard-native-real-corpus": "results/standard-native-real-corpus.junit.xml",
}
RELEASE_QUALIFICATION_V2_RESULT_PATHS = {
    **{
        name: relative.removesuffix(".xml") + ".summary.json"
        for name, relative in RELEASE_QUALIFICATION_V2_JUNIT_PATHS.items()
    },
    "production-web-build": "results/web-build.json",
    "production-chromium-e2e": "results/browser-e2e.json",
}
RELEASE_QUALIFICATION_V2_LOG_PATHS = {
    name: f"logs/{index:02d}-{name}.log"
    for index, name in enumerate(RELEASE_QUALIFICATION_V2_COMMAND_NAMES, start=1)
}
MAXIMUM_JUNIT_BYTES = 16 * 1024 * 1024
MAXIMUM_JUNIT_TESTCASES = 10_000
MAXIMUM_JUNIT_XML_ELEMENTS = 100_000


def release_qualification_v2_command_documents() -> tuple[dict[str, Any], ...]:
    """Return the one canonical, path-normalized V2 command inventory."""

    pytest_prefix = ("uv", "run", "--frozen", "--no-sync", "pytest", "-p", "no:cacheprovider")

    def pytest_command(name: str, *tests: str) -> dict[str, Any]:
        junit = RELEASE_QUALIFICATION_V2_JUNIT_PATHS[name]
        return {
            "name": name,
            "argv": [
                *pytest_prefix,
                *tests,
                f"--junitxml=$EVIDENCE_ROOT/$RUN_ID/{junit}",
            ],
            "cwd": ".",
            "log_relative_path": RELEASE_QUALIFICATION_V2_LOG_PATHS[name],
        }

    return (
        pytest_command(
            "protected-real-corpus",
            (
                "tests/analysis/test_standard_real_corpus_e2e.py::"
                "test_trial132_one_path_one_coarse_window_benchmark_smoke"
            ),
            (
                "tests/integration/test_standard_v2_operational_vertical.py::"
                "test_standard_v2_four_path_operational_vertical"
            ),
        ),
        pytest_command(
            "standard-native-science",
            "tests/analysis/test_standard_native_scientific_equivalence.py",
            "tests/analysis/test_standard_native_stateful.py",
            "tests/analysis/test_standard_native_full_capture_glrt.py",
            "tests/analysis/test_standard_native_qam.py",
            "tests/analysis/test_standard_native_path_report.py",
            "tests/contracts/test_standard_path_input_bind_v4.py",
        ),
        pytest_command(
            "standard-native-postgresql",
            (
                "tests/processing/test_standard_native_operational_vertical.py::"
                "test_real_postgres_standard_native_operational_vertical"
            ),
            (
                "tests/processing/test_standard_native_presentation_vertical.py::"
                "test_real_postgres_promoted_gapped_native_run_is_presented_as_current_partial"
            ),
            (
                "tests/processing/test_mixed_rate_standard_native_operational_vertical.py::"
                "test_real_postgres_mixed_capture_standard_png_and_browser_vertical"
            ),
            (
                "tests/processing/test_mixed_rate_standard_native_operational_vertical.py::"
                "test_real_postgres_production_single_rx_all_rate_vertical"
            ),
            (
                "tests/processing/test_mixed_rate_standard_native_operational_vertical.py::"
                "test_real_postgres_direct_async_capture_analysis_png_and_browser_vertical"
            ),
        ),
        pytest_command(
            "standard-native-real-corpus",
            "-m",
            "real_corpus",
            "tests/integration/test_standard_native_real_corpus.py",
        ),
        {
            "name": "production-web-build",
            "argv": [
                "npm",
                "--prefix",
                "$SCRATCH_ROOT/web",
                "run",
                "qualify:release",
                "--",
                "--outDir",
                "$SCRATCH_ROOT/web-dist",
            ],
            "cwd": ".",
            "log_relative_path": RELEASE_QUALIFICATION_V2_LOG_PATHS["production-web-build"],
        },
        {
            "name": "production-chromium-e2e",
            "argv": [
                "npm",
                "run",
                "test:e2e:production",
                "--",
                "--output",
                "$EVIDENCE_ROOT/$RUN_ID/results/playwright",
            ],
            "cwd": "web",
            "log_relative_path": RELEASE_QUALIFICATION_V2_LOG_PATHS["production-chromium-e2e"],
        },
    )


def release_qualification_v2_definition(
    *,
    run_id: str,
    started_utc: str,
    git_revision: str,
    python_version: str,
    platform_identity: str,
    uv_lock_sha256: str,
    package_lock_sha256: str,
    corpus_manifest_sha256: str,
    database_identity: str,
    protected_corpus_root: str,
    native_rate_corpus_root: str,
) -> dict[str, Any]:
    """Build the complete canonical V2 definition without filesystem access."""

    return {
        "schema": RELEASE_QUALIFICATION_V2_SCHEMA,
        "run_id": run_id,
        "started_utc": started_utc,
        "source": {
            "git_revision": git_revision,
            "git_clean": True,
            "python": python_version,
            "platform": platform_identity,
            "uv_lock_sha256": uv_lock_sha256,
            "package_lock_sha256": package_lock_sha256,
            "corpus_manifest_sha256": corpus_manifest_sha256,
        },
        "isolation": {
            "database": database_identity,
            "database_policy": "dedicated qualification database; unique test schemas",
            "database_initial_schemas": ["public"],
            "generated_data": "test-owned temporary RecordingStore roots",
            "protected_corpus_root": protected_corpus_root,
            "protected_corpus_access": "read-only",
            "native_rate_corpus_root": native_rate_corpus_root,
            "native_rate_corpus_access": "read-only",
            "qnap_access": "forbidden",
        },
        "commands": list(release_qualification_v2_command_documents()),
    }


def release_qualification_schema_version(document: Mapping[str, Any]) -> Literal[1, 2]:
    """Identify both published majors without treating V1 as V2 authority."""

    schema = document.get("schema")
    if schema == RELEASE_QUALIFICATION_V1_SCHEMA:
        return 1
    if schema == RELEASE_QUALIFICATION_V2_SCHEMA:
        return 2
    raise ValueError("release qualification schema is unsupported")


def summarize_pytest_junit_v1(
    payload: bytes,
    *,
    command_name: str,
    junit_relative_path: str,
) -> dict[str, Any]:
    """Parse one bounded JUnit receipt and return its closed semantic summary."""

    if not payload or len(payload) > MAXIMUM_JUNIT_BYTES:
        raise ValueError("JUnit receipt is empty or exceeds the 16 MiB boundary")
    lowered = payload.lower()
    if b"<!doctype" in lowered or b"<!entity" in lowered:
        raise ValueError("JUnit receipt contains a forbidden document type or entity")
    try:
        root = ET.fromstring(payload)
    except ET.ParseError as error:
        raise ValueError("JUnit receipt is malformed XML") from error
    if root.tag not in {"testsuite", "testsuites"}:
        raise ValueError("JUnit receipt root is not testsuite/testsuites")
    if sum(1 for _element in root.iter()) > MAXIMUM_JUNIT_XML_ELEMENTS:
        raise ValueError("JUnit receipt exceeds the XML element boundary")
    suites = (root,) if root.tag == "testsuite" else tuple(root.findall("testsuite"))
    if not suites:
        raise ValueError("JUnit receipt contains no test suites")
    testcases = tuple(root.iter("testcase"))
    if not testcases or len(testcases) > MAXIMUM_JUNIT_TESTCASES:
        raise ValueError("JUnit receipt has zero tests or exceeds the testcase boundary")
    identities: list[str] = []
    failures = 0
    errors = 0
    skipped = 0
    for testcase in testcases:
        name = testcase.get("name")
        classname = testcase.get("classname")
        if not name or not classname:
            raise ValueError("JUnit testcase lacks a name or classname")
        identities.append(f"{classname}::{name}")
        failures += sum(1 for child in testcase if child.tag == "failure")
        errors += sum(1 for child in testcase if child.tag == "error")
        skipped += sum(1 for child in testcase if child.tag == "skipped")
    for suite in suites:
        suite_testcases = tuple(suite.findall("testcase"))
        declared: dict[str, int] = {}
        for attribute in ("tests", "failures", "errors", "skipped"):
            value = suite.get(attribute)
            try:
                parsed = int(value or "")
            except ValueError as error:
                raise ValueError(f"JUnit testsuite has no valid {attribute!r} count") from error
            if parsed < 0:
                raise ValueError(f"JUnit testsuite has a negative {attribute!r} count")
            declared[attribute] = parsed
        observed = {
            "tests": len(suite_testcases),
            "failures": sum(
                1 for testcase in suite_testcases for child in testcase if child.tag == "failure"
            ),
            "errors": sum(
                1 for testcase in suite_testcases for child in testcase if child.tag == "error"
            ),
            "skipped": sum(
                1 for testcase in suite_testcases for child in testcase if child.tag == "skipped"
            ),
        }
        if declared != observed:
            raise ValueError("JUnit testsuite declared counts do not match its testcases")
    if failures or errors or skipped:
        raise ValueError(
            "JUnit receipt is not an all-pass result: "
            f"failures={failures} errors={errors} skipped={skipped}"
        )
    identity_payload = json.dumps(
        identities,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return {
        "schema_version": 1,
        "kind": "pytest-junit-summary",
        "command_name": command_name,
        "junit_relative_path": junit_relative_path,
        "junit_sha256": hashlib.sha256(payload).hexdigest(),
        "tests": len(testcases),
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "testcase_inventory_sha256": hashlib.sha256(identity_payload).hexdigest(),
        "passed": True,
    }


def validate_pytest_junit_summary_v1(
    summary: Mapping[str, Any],
    payload: bytes,
    *,
    command_name: str,
    junit_relative_path: str,
) -> None:
    """Require an exact persisted summary of the supplied JUnit bytes."""

    expected = summarize_pytest_junit_v1(
        payload,
        command_name=command_name,
        junit_relative_path=junit_relative_path,
    )
    if dict(summary) != expected:
        raise ValueError("persisted JUnit summary does not match the exact XML receipt")


def as_json_object(value: object) -> dict[str, Any]:
    """Narrow a decoded JSON value for callers loading this module dynamically."""

    if not isinstance(value, dict):
        raise ValueError("release qualification document must be a JSON object")
    return cast(dict[str, Any], value)
