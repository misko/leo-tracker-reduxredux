"""Pure, versioned authority for release-qualification evidence.

V1 documents remain historical persisted evidence.  V2 is additive and is the
first release-qualification contract whose exact command and result inventory
is suitable for production cutover authority.  V3 leaves both published
contracts untouched and narrows the default gate to current recording formats.
Its deterministic lane metadata is suitable for content-addressed reuse.
"""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from typing import Any, Literal, cast

RELEASE_QUALIFICATION_V1_SCHEMA = "org.leo.release-qualification/v1"
RELEASE_QUALIFICATION_V2_SCHEMA = "org.leo.release-qualification/v2"
RELEASE_QUALIFICATION_V3_SCHEMA = "org.leo.release-qualification/v3"
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
RELEASE_QUALIFICATION_V3_COMMAND_NAMES = (
    "protected-real-corpus",
    "current-native-science",
    "current-native-postgresql",
    "production-web-build",
    "production-chromium-e2e",
)
RELEASE_QUALIFICATION_V3_HISTORICAL_COMMAND_NAMES = ("historical-recording-postgresql",)
RELEASE_QUALIFICATION_V3_ALL_COMMAND_NAMES = (
    *RELEASE_QUALIFICATION_V3_COMMAND_NAMES,
    *RELEASE_QUALIFICATION_V3_HISTORICAL_COMMAND_NAMES,
)
RELEASE_QUALIFICATION_V3_JUNIT_PATHS = {
    "protected-real-corpus": "results/protected-real-corpus.junit.xml",
    "current-native-science": "results/current-native-science.junit.xml",
    "current-native-postgresql": "results/current-native-postgresql.junit.xml",
    "historical-recording-postgresql": "results/historical-recording-postgresql.junit.xml",
}
RELEASE_QUALIFICATION_V3_RESULT_PATHS = {
    **{
        name: relative.removesuffix(".xml") + ".summary.json"
        for name, relative in RELEASE_QUALIFICATION_V3_JUNIT_PATHS.items()
    },
    "production-web-build": "results/web-build.json",
    "production-chromium-e2e": "results/browser-e2e.json",
}
RELEASE_QUALIFICATION_V3_LOG_PATHS = {
    name: f"logs/{index:02d}-{name}.log"
    for index, name in enumerate(RELEASE_QUALIFICATION_V3_ALL_COMMAND_NAMES, start=1)
}
_V3_COMMON_INPUT_PATHS = (
    "pyproject.toml",
    "uv.lock",
    "src/leo/__init__.py",
    "src/leo/qualification/release.py",
    "src/leo/qualification/release_contract.py",
)
_V3_SCIENCE_SOURCE_PATHS = (
    "src/leo/analysis",
    "src/leo/artifacts",
    "src/leo/contracts",
    "src/leo/domain",
    "src/leo/pipeline",
    "src/leo/storage",
)
_V3_SCIENCE_TEST_PATHS = (
    "tests/conftest.py",
    "tests/analysis/test_standard_native_scientific_equivalence.py",
    "tests/analysis/test_standard_native_stateful.py",
    "tests/analysis/test_standard_native_full_capture_glrt.py",
    "tests/analysis/test_standard_native_qam.py",
    "tests/analysis/test_standard_native_path_report.py",
    "tests/analysis/test_standard_native_observability.py",
    "tests/analysis/test_standard_native_rate_equivalence.py",
)
_V3_POSTGRESQL_SOURCE_PATHS = (
    "alembic.ini",
    "migrations",
    "profiles",
    "src/leo/acquisition",
    "src/leo/analysis",
    "src/leo/api",
    "src/leo/application",
    "src/leo/artifacts",
    "src/leo/catalog",
    "src/leo/contracts",
    "src/leo/domain",
    "src/leo/operations",
    "src/leo/pipeline",
    "src/leo/presentation",
    "src/leo/processing",
    "src/leo/radio",
    "src/leo/station",
    "src/leo/storage",
)
_V3_CHROMIUM_SOURCE_PATHS = (
    *_V3_POSTGRESQL_SOURCE_PATHS,
    "src/leo/scanner",
    "src/leo/sky",
)
RELEASE_QUALIFICATION_V3_LANE_INPUT_PATHS = {
    "protected-real-corpus": (
        *_V3_COMMON_INPUT_PATHS,
        *_V3_SCIENCE_SOURCE_PATHS,
        "config/analysis",
        "corpus",
        "tests/conftest.py",
        "tests/analysis/test_standard_real_corpus_e2e.py",
    ),
    "current-native-science": (
        *_V3_COMMON_INPUT_PATHS,
        *_V3_SCIENCE_SOURCE_PATHS,
        "config/analysis",
        *_V3_SCIENCE_TEST_PATHS,
    ),
    "current-native-postgresql": (
        *_V3_COMMON_INPUT_PATHS,
        *_V3_POSTGRESQL_SOURCE_PATHS,
        "tests/conftest.py",
        "tests/postgres_support.py",
        "tests/processing/conftest.py",
        "tests/processing/test_mixed_rate_standard_native_operational_vertical.py",
    ),
    "production-web-build": (
        *_V3_COMMON_INPUT_PATHS,
        "web",
    ),
    "production-chromium-e2e": (
        *_V3_COMMON_INPUT_PATHS,
        *_V3_CHROMIUM_SOURCE_PATHS,
        "tests/e2e",
        "tests/postgres_support.py",
        "web",
    ),
    "historical-recording-postgresql": (
        *_V3_COMMON_INPUT_PATHS,
        *_V3_POSTGRESQL_SOURCE_PATHS,
        "tests/conftest.py",
        "tests/postgres_support.py",
        "tests/processing/conftest.py",
        "tests/processing/test_standard_native_operational_vertical.py",
        "tests/processing/test_standard_native_presentation_vertical.py",
        "tests/processing/test_mixed_rate_standard_native_operational_vertical.py",
    ),
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


def release_qualification_v3_command_documents(
    *,
    include_historical: bool = False,
) -> tuple[dict[str, Any], ...]:
    """Return V3's current-format lanes and optional non-release historical lanes."""

    pytest_prefix = ("uv", "run", "--frozen", "--no-sync", "pytest", "-p", "no:cacheprovider")

    def pytest_command(
        name: str,
        *tests: str,
        resource_units: int,
        database_access: bool = False,
        release_blocking: bool = True,
    ) -> dict[str, Any]:
        junit = RELEASE_QUALIFICATION_V3_JUNIT_PATHS[name]
        return {
            "name": name,
            "argv": [
                *pytest_prefix,
                *tests,
                f"--junitxml=$EVIDENCE_ROOT/$RUN_ID/{junit}",
            ],
            "cwd": ".",
            "log_relative_path": RELEASE_QUALIFICATION_V3_LOG_PATHS[name],
            "resource_units": resource_units,
            "database_access": database_access,
            "depends_on": [],
            "release_blocking": release_blocking,
        }

    commands = [
        pytest_command(
            "protected-real-corpus",
            (
                "tests/analysis/test_standard_real_corpus_e2e.py::"
                "test_trial132_one_path_one_coarse_window_benchmark_smoke"
            ),
            resource_units=1,
        ),
        pytest_command(
            "current-native-science",
            "tests/analysis/test_standard_native_scientific_equivalence.py",
            "tests/analysis/test_standard_native_stateful.py",
            "tests/analysis/test_standard_native_full_capture_glrt.py",
            "tests/analysis/test_standard_native_qam.py",
            "tests/analysis/test_standard_native_path_report.py",
            resource_units=2,
        ),
        pytest_command(
            "current-native-postgresql",
            (
                "tests/processing/test_mixed_rate_standard_native_operational_vertical.py::"
                "test_real_postgres_direct_async_capture_analysis_png_and_browser_vertical"
            ),
            resource_units=2,
            database_access=True,
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
            "log_relative_path": RELEASE_QUALIFICATION_V3_LOG_PATHS["production-web-build"],
            "resource_units": 1,
            "database_access": False,
            "depends_on": [],
            "release_blocking": True,
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
            "log_relative_path": RELEASE_QUALIFICATION_V3_LOG_PATHS["production-chromium-e2e"],
            "resource_units": 1,
            "database_access": True,
            "depends_on": ["production-web-build"],
            "release_blocking": True,
        },
    ]
    if include_historical:
        commands.extend(
            (
                pytest_command(
                    "historical-recording-postgresql",
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
                        "test_real_postgres_production_single_rx_all_rate_vertical"
                    ),
                    resource_units=2,
                    database_access=True,
                    release_blocking=False,
                ),
            )
        )
    return tuple(commands)


def release_qualification_v3_lane_metadata(
    command: Mapping[str, Any],
    *,
    input_digests: Mapping[str, str],
) -> dict[str, Any]:
    """Close one lane's reusable identity over its command and exact inputs."""

    command_document = dict(command)
    command_sha256 = _canonical_sha256(command_document)
    ordered_inputs = {name: input_digests[name] for name in sorted(input_digests)}
    return {
        "command_sha256": command_sha256,
        "input_digests": ordered_inputs,
        "reuse_key_sha256": _canonical_sha256(
            {
                "schema": RELEASE_QUALIFICATION_V3_SCHEMA,
                "command_sha256": command_sha256,
                "input_digests": ordered_inputs,
            }
        ),
    }


def release_qualification_v3_inventory_digest(
    files: Sequence[Mapping[str, Any]],
) -> str:
    """Hash one ordered regular-file inventory with V3 canonical JSON."""

    return _canonical_sha256({"files": [dict(item) for item in files]})


def release_qualification_v3_runtime_digest(
    *,
    python_version: str,
    platform_identity: str,
) -> str:
    """Hash the execution ABI identity shared by Python qualification lanes."""

    return _canonical_sha256({"python": python_version, "platform": platform_identity})


def release_qualification_v3_lane_input_digests(
    commands: Sequence[Mapping[str, Any]],
    *,
    path_digests: Mapping[str, str],
    python_runtime_sha256: str,
) -> dict[str, dict[str, str]]:
    """Map independently measured bounded path closures onto exact lanes."""

    command_names = tuple(command.get("name") for command in commands)
    if any(
        not isinstance(name, str) or name not in RELEASE_QUALIFICATION_V3_LANE_INPUT_PATHS
        for name in command_names
    ) or len(set(command_names)) != len(command_names):
        raise ValueError("V3 command inventory has no unique string names")
    names = cast(tuple[str, ...], command_names)
    expected_paths = {
        path for name in names for path in RELEASE_QUALIFICATION_V3_LANE_INPUT_PATHS[name]
    }
    if set(path_digests) != expected_paths or any(
        not _is_sha256_text(value) for value in path_digests.values()
    ):
        raise ValueError("V3 bounded path-digest inventory is not exact")
    if not _is_sha256_text(python_runtime_sha256):
        raise ValueError("V3 Python runtime digest is malformed")
    result: dict[str, dict[str, str]] = {}
    for name in names:
        if name in result or name not in RELEASE_QUALIFICATION_V3_LANE_INPUT_PATHS:
            raise ValueError("V3 command inventory has no unique string names")
        inputs = {
            f"path:{path}": path_digests[path]
            for path in RELEASE_QUALIFICATION_V3_LANE_INPUT_PATHS[name]
        }
        if name != "production-web-build":
            inputs["python-runtime"] = python_runtime_sha256
        result[name] = inputs
    return result


def validate_reusable_release_qualification_v3_lane(
    outcome: Mapping[str, Any],
    expected_command: Mapping[str, Any],
) -> None:
    """Recognize one exact passing V3 lane independently of its source revision."""

    expected_keys = {
        "name",
        "exit_code",
        "passed",
        "release_blocking",
        "resource_units",
        "database_access",
        "depends_on",
        "command_sha256",
        "reuse_key_sha256",
        "started_utc",
        "finished_utc",
        "duration_seconds",
        "log_relative_path",
        "log_sha256",
        "result_relative_path",
        "result_sha256",
        "validation_error",
    }
    if set(outcome) != expected_keys:
        raise ValueError("reusable V3 lane outcome schema is not closed")
    metadata = expected_command.get("lane_metadata")
    if not isinstance(metadata, Mapping):
        raise ValueError("expected V3 lane has no reuse metadata")
    name = expected_command.get("name")
    expected_result = RELEASE_QUALIFICATION_V3_RESULT_PATHS.get(str(name))
    if (
        outcome.get("name") != name
        or outcome.get("exit_code") != 0
        or outcome.get("passed") is not True
        or outcome.get("validation_error") is not None
        or outcome.get("release_blocking") is not expected_command.get("release_blocking")
        or outcome.get("resource_units") != expected_command.get("resource_units")
        or outcome.get("database_access") is not expected_command.get("database_access")
        or outcome.get("depends_on") != expected_command.get("depends_on")
        or outcome.get("command_sha256") != metadata.get("command_sha256")
        or outcome.get("reuse_key_sha256") != metadata.get("reuse_key_sha256")
        or outcome.get("log_relative_path") != expected_command.get("log_relative_path")
        or outcome.get("result_relative_path") != expected_result
        or not _is_sha256_text(outcome.get("log_sha256"))
        or not _is_sha256_text(outcome.get("result_sha256"))
        or type(outcome.get("duration_seconds")) not in {int, float}
        or not isinstance(outcome.get("started_utc"), str)
        or not isinstance(outcome.get("finished_utc"), str)
    ):
        raise ValueError("V3 lane is not an exact reusable passing result")


def _is_sha256_text(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def release_qualification_v3_definition(
    *,
    run_id: str,
    started_utc: str,
    git_revision: str,
    git_tree: str,
    source_identity_kind: str,
    python_version: str,
    platform_identity: str,
    uv_lock_sha256: str,
    package_lock_sha256: str,
    corpus_manifest_sha256: str,
    database_identity: str,
    protected_corpus_root: str,
    native_rate_corpus_root: str,
    maximum_resource_units: int,
    include_historical: bool,
    lane_input_digests: Mapping[str, Mapping[str, str]],
) -> dict[str, Any]:
    """Build the complete canonical V3 definition without filesystem access."""

    commands = release_qualification_v3_command_documents(include_historical=include_historical)
    if set(lane_input_digests) != {command["name"] for command in commands}:
        raise ValueError("V3 lane input-digest inventory is not exact")
    return {
        "schema": RELEASE_QUALIFICATION_V3_SCHEMA,
        "run_id": run_id,
        "started_utc": started_utc,
        "source": {
            "git_revision": git_revision,
            "git_tree": git_tree,
            "git_clean": True,
            "source_identity_kind": source_identity_kind,
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
        "execution": {
            "scheduler": "bounded-resource-dag-v1",
            "maximum_resource_units": maximum_resource_units,
            "database_lanes_are_exclusive": True,
            "include_historical": include_historical,
        },
        "commands": [
            {
                **command,
                "lane_metadata": release_qualification_v3_lane_metadata(
                    command,
                    input_digests=lane_input_digests[command["name"]],
                ),
            }
            for command in commands
        ],
    }


def _canonical_sha256(document: Mapping[str, Any]) -> str:
    payload = json.dumps(
        dict(document),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


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


def release_qualification_schema_version(document: Mapping[str, Any]) -> Literal[1, 2, 3]:
    """Identify published majors without treating an old receipt as new authority."""

    schema = document.get("schema")
    if schema == RELEASE_QUALIFICATION_V1_SCHEMA:
        return 1
    if schema == RELEASE_QUALIFICATION_V2_SCHEMA:
        return 2
    if schema == RELEASE_QUALIFICATION_V3_SCHEMA:
        return 3
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
