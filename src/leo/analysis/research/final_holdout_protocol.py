"""Fail-closed validator for the prospectively frozen final holdout protocol."""

from __future__ import annotations

import hashlib
import json
import math
import re
import subprocess
from pathlib import Path
from typing import Any, cast

from leo.analysis.research.doppler_association_authority import (
    CaptureArtifactAuthorityV1,
    NominalRfAuthorityV1,
    ObserverSiteAuthorityV1,
    StreamUtcAuthorityV1,
)
from leo.analysis.research.doppler_holdout_pre_response import (
    DEFAULT_STRICT_PAST_CONFIGS,
)
from leo.contracts.digests import canonical_digest

SCHEMA = "org.leo.research.final-doppler-holdout-satellite/v1"
SELECTOR_PATH = "reports/figures/2026_08_26_doppler_holdout_selector_v2/derived-manifest-v2.json"
SELECTOR_FILE_SHA256 = "sha256:aa1116aeb69181ec631be20500d35449457db830dccb454245a36f646763556a"
SELECTOR_SEMANTIC_DIGEST = "sha256:99a914335caa8501745325c265b67b68c22317fa399e6c6a03e27fe64400627b"
DATASET_POLICY_PATH = "config/analysis/doppler-experiment-dataset-policy-v1.json"
DATASET_POLICY_SHA256 = "sha256:5eb6751b5e006c23b5186fd3e57801c58fa79cd47e3c1d66f61af2d049c00a3e"
DATASET_POLICY_COMMIT = "2e17b4477b38494e14bab7ff39303cf3a219bb03e"
SELECTOR_PROTOCOL_COMMIT = "d1aab4f65cc0bd69d9a25c025a0eca8967b49fe5"
SELECTOR_PROTOCOL_PATH = "config/analysis/doppler-holdout-feasibility-protocol-v2.json"
SELECTOR_PROTOCOL_SHA256 = "sha256:876a829d2646c7a6c0003c68e96d8efd73e11a4b30e60ae245adc0b8f18e9910"
TARGET_COUNT = 5_413
CAPTURE_IDS = (
    "cap-20260825T022235-0afd1298f096",
    "cap-20260825T030000-49e936766343",
    "cap-20260825T031521-ec8adc0e9426",
    "cap-20260825T033028-374381fbcd3a",
    "cap-20260825T033302-80fddf217eb5",
    "cap-20260825T034929-bc0480bdb4a8",
    "cap-20260825T035201-d0abaead734c",
    "cap-20260825T041207-a5f08ab5bd42",
    "cap-20260825T043656-2da9e806d487",
    "cap-20260825T050946-ab916a6d0eee",
)
TARGET_COUNTS = (911, 355, 920, 918, 442, 112, 324, 482, 457, 492)

# These values were read from the ten digest-pinned recording manifests before
# propagation or odd-Qin access.  Keeping them independent of the protocol JSON
# prevents a self-consistent but substituted authority from passing validation.
_EXPECTED_RF_UTC: dict[str, tuple[object, ...]] = {
    CAPTURE_IDS[0]: (
        "stream-0",
        "radio_pluto_5d4d",
        "1040005e0b100007100010000bf33a5d4d",
        0,
        "rx_lnb_a",
        "lower",
        1787624558335142788,
        1787624558335626964,
        1787624558336111140,
        959687498,
        10709687498,
    ),
    CAPTURE_IDS[1]: (
        "stream-1",
        "radio_pluto_19f2",
        "10400056f695001322002d0010ad1719f2",
        1,
        "rx_lnb_d",
        "upper",
        1787626803461606473,
        1787626803462157417,
        1787626803462708361,
        1940312500,
        11690312500,
    ),
    CAPTURE_IDS[2]: (
        "stream-1",
        "radio_pluto_19f2",
        "10400056f695001322002d0010ad1719f2",
        1,
        "rx_lnb_d",
        "lower",
        1787627724955300522,
        1787627724955791026,
        1787627724956281530,
        1709687500,
        11459687500,
    ),
    CAPTURE_IDS[3]: (
        "stream-1",
        "radio_pluto_19f2",
        "10400056f695001322002d0010ad1719f2",
        0,
        "rx_lnb_c",
        "lower",
        1787628631779108051,
        1787628631779573671,
        1787628631780039291,
        1459687498,
        11209687498,
    ),
    CAPTURE_IDS[4]: (
        "stream-1",
        "radio_pluto_19f2",
        "10400056f695001322002d0010ad1719f2",
        1,
        "rx_lnb_d",
        "lower",
        1787628785712695304,
        1787628785713502949,
        1787628785714310594,
        1209687498,
        10959687498,
    ),
    CAPTURE_IDS[5]: (
        "stream-0",
        "radio_pluto_5d4d",
        "1040005e0b100007100010000bf33a5d4d",
        1,
        "rx_lnb_b",
        "upper",
        1787629772791972357,
        1787629772792594981,
        1787629772793217605,
        1440312500,
        11190312500,
    ),
    CAPTURE_IDS[6]: (
        "stream-1",
        "radio_pluto_19f2",
        "10400056f695001322002d0010ad1719f2",
        1,
        "rx_lnb_d",
        "lower",
        1787629925215632487,
        1787629925216153660,
        1787629925216674833,
        1709687500,
        11459687500,
    ),
    CAPTURE_IDS[7]: (
        "stream-1",
        "radio_pluto_19f2",
        "10400056f695001322002d0010ad1719f2",
        1,
        "rx_lnb_d",
        "upper",
        1787631130623664319,
        1787631130624334590,
        1787631130625004861,
        1440312500,
        11190312500,
    ),
    CAPTURE_IDS[8]: (
        "stream-1",
        "radio_pluto_19f2",
        "10400056f695001322002d0010ad1719f2",
        1,
        "rx_lnb_d",
        "lower",
        1787632619815688065,
        1787632619816402675,
        1787632619817117285,
        959687498,
        10709687498,
    ),
    CAPTURE_IDS[9]: (
        "stream-0",
        "radio_pluto_5d4d",
        "1040005e0b100007100010000bf33a5d4d",
        1,
        "rx_lnb_b",
        "lower",
        1787634590039907533,
        1787634590040376426,
        1787634590040845319,
        959687498,
        10709687498,
    ),
}

_SNAPSHOTS = {
    "sha256:dc8f5f59ab133df08c921c29157b56354179ae4e33fafea0853a718cd7122755": (
        "sha256:98697f3c8af9321baa3d857662da0798e437fa374f274fc71c295ec52ca3ddac",
        "2026-08-24T23:37:00.001819Z",
        "/mnt/qnap01/mouse9911/tle/snapshots/space-track/starlink/2026/08/24/20260824T233700Z-dc8f5f59ab13.json",
        "/mnt/qnap01/mouse9911/tle/raw/space-track/dc8f5f59ab133df08c921c29157b56354179ae4e33fafea0853a718cd7122755.tle",
    ),
    "sha256:a8548f683aaf7acb1bd8e489932aef22c2815d5c1e434b3435ff574b0186dda3": (
        "sha256:2e3c3c03b53e4b96480975cc119a13c984fe4d27cd6dd8b6e8902c7dfc65b75b",
        "2026-08-25T01:37:00.001224Z",
        "/mnt/qnap01/mouse9911/tle/snapshots/space-track/starlink/2026/08/25/20260825T013700Z-a8548f683aaf.json",
        "/mnt/qnap01/mouse9911/tle/raw/space-track/a8548f683aaf7acb1bd8e489932aef22c2815d5c1e434b3435ff574b0186dda3.tle",
    ),
    "sha256:0637ab6c9585fe053213f456ce88bb0b9cd536d1470b27010cd5f81b4b4b3f85": (
        "sha256:242d44dbc572113c58831c1f62f8007bdb695a595f267d2d9b879fb3c31a0616",
        "2026-08-25T03:37:00.000828Z",
        "/mnt/qnap01/mouse9911/tle/snapshots/space-track/starlink/2026/08/25/20260825T033700Z-0637ab6c9585.json",
        "/mnt/qnap01/mouse9911/tle/raw/space-track/0637ab6c9585fe053213f456ce88bb0b9cd536d1470b27010cd5f81b4b4b3f85.tle",
    ),
    "sha256:ca5345a88ba794fcbc0c2e5f14786c130e8f0bbd9a744001983d46b6dbda9c30": (
        "sha256:d604e9f16fcb4279e8f2af93a5d44eee51c256eb1baa0ce4e33491cbb0f163d0",
        "2026-08-25T05:37:00.001167Z",
        "/mnt/qnap01/mouse9911/tle/snapshots/space-track/starlink/2026/08/25/20260825T053700Z-ca5345a88ba7.json",
        "/mnt/qnap01/mouse9911/tle/raw/space-track/ca5345a88ba794fcbc0c2e5f14786c130e8f0bbd9a744001983d46b6dbda9c30.tle",
    ),
}

_EXPECTED_CHUNKS = (
    (
        CAPTURE_IDS[0],
        "stream-0",
        "radio-1040005e0b100007100010000bf33a5d4d/iq-000006.ci16.zst",
        100663296,
        16777216,
        "sha256:8b9a108d54bf6eebbc5aa7380f26ec0081bc3bb884006eea556843b3449765a1",
    ),
    (
        CAPTURE_IDS[1],
        "stream-1",
        "radio-10400056f695001322002d0010ad1719f2/iq-000001.ci16.zst",
        16777216,
        16777216,
        "sha256:9b6dd1be92039504e64afdb14a6693da4841867302f9f488dd3bfbe45e1415d5",
    ),
    (
        CAPTURE_IDS[2],
        "stream-1",
        "radio-10400056f695001322002d0010ad1719f2/iq-000005.ci16.zst",
        83886080,
        16777216,
        "sha256:d9055b60c5833d548fee78580bdad5e01fc83596876944feb84ea5dd2e91e1f5",
    ),
    (
        CAPTURE_IDS[3],
        "stream-1",
        "radio-10400056f695001322002d0010ad1719f2/iq-000005.ci16.zst",
        83886080,
        16777216,
        "sha256:bf73c664ac13e3b4489eaa44435f0392ddfbbd9a831d008401ada673456b3f9a",
    ),
    (
        CAPTURE_IDS[4],
        "stream-1",
        "radio-10400056f695001322002d0010ad1719f2/iq-000000.ci16.zst",
        0,
        16777216,
        "sha256:083bf5dc5d91778320f9ad8496009f42f658229d2362e6e49566c9b4a5cbcce2",
    ),
    (
        CAPTURE_IDS[5],
        "stream-0",
        "radio-1040005e0b100007100010000bf33a5d4d/iq-000002.ci16.zst",
        33554432,
        16777216,
        "sha256:cfca8aed0465f05bdee39b04d71021fedc7a52800a34124d115c0f9ceb44988f",
    ),
    (
        CAPTURE_IDS[6],
        "stream-1",
        "radio-10400056f695001322002d0010ad1719f2/iq-000003.ci16.zst",
        50331648,
        16777216,
        "sha256:9610dd5af0e22d7d41fae47a8ed18f4253420ff8aa1d800b0bf0622230324622",
    ),
    (
        CAPTURE_IDS[7],
        "stream-1",
        "radio-10400056f695001322002d0010ad1719f2/iq-000008.ci16.zst",
        134217728,
        15782272,
        "sha256:153b1f42dcb3dd644a8622b55603c974319f869edd2409f273784a25b67679fc",
    ),
    (
        CAPTURE_IDS[8],
        "stream-1",
        "radio-10400056f695001322002d0010ad1719f2/iq-000005.ci16.zst",
        83886080,
        16777216,
        "sha256:aefb4bc1e3e40c95a7d154a2c567aac5b731b7259ed70605dd9943fe9f1918b6",
    ),
    (
        CAPTURE_IDS[9],
        "stream-0",
        "radio-1040005e0b100007100010000bf33a5d4d/iq-000007.ci16.zst",
        117440512,
        16777216,
        "sha256:118fcab6041718acf99876a935209b6c7a361a6bfbd6b9c3c3a3f36f5d77b868",
    ),
    (
        CAPTURE_IDS[9],
        "stream-0",
        "radio-1040005e0b100007100010000bf33a5d4d/iq-000008.ci16.zst",
        134217728,
        15782272,
        "sha256:ce49f228bc2967f505afdb9c7e933ea4f85a6bd7e902b8ccbc39b8cab2cbc6d9",
    ),
)

_IMPLEMENTATION_KEYS = {
    "src/leo/analysis/qam/__init__.py",
    "src/leo/analysis/research/doppler_association_authority.py",
    "src/leo/analysis/qam/pilot.py",
    "src/leo/analysis/qam/pilot_odd.py",
    "src/leo/analysis/research/doppler_holdout_odd_adapter.py",
    "src/leo/analysis/research/doppler_holdout_pre_response.py",
    "src/leo/analysis/research/doppler_holdout_response_v2.py",
    "src/leo/analysis/research/final_doppler_holdout.py",
    "src/leo/analysis/research/final_holdout_protocol.py",
    "src/leo/analysis/research/final_holdout_satellite.py",
    "src/leo/analysis/research/legacy_tle_snapshot.py",
    "src/leo/analysis/starlink/templates.py",
    "src/leo/sky/doppler.py",
    "src/leo/sky/propagation.py",
    "src/leo/sky/sampling.py",
    "src/leo/sky/screening.py",
    "src/leo/sky/sites.py",
    "src/leo/storage/pinned.py",
    "src/leo/storage/store.py",
    "tools/run_final_doppler_holdout.py",
    "uv.lock",
}

_TOP_LEVEL_KEYS = {
    "schema",
    "status",
    "chronology",
    "dataset_policy",
    "selector_v2",
    "upstream_conditioning",
    "captures",
    "site",
    "tle_authority",
    "authorized_odd_chunks",
    "strict_past_estimators",
    "odd_response",
    "scoring",
    "association",
    "corrected_fixed500",
    "calibrated_intervals",
    "implementation_sha256",
    "protocol_digest",
}


def load_and_validate_final_protocol(path: Path, *, repository_root: Path) -> dict[str, Any]:
    """Load one protocol and independently verify every execution binding."""

    document = _load_json_without_duplicate_keys(path)
    if not isinstance(document, dict) or document.get("schema") != SCHEMA:
        raise ValueError("unsupported final holdout protocol")
    _require_exact_keys(document, _TOP_LEVEL_KEYS, "protocol")
    if document.get("status") != "frozen_before_propagation_ranking_and_odd_access":
        raise ValueError("final holdout chronology is not frozen")
    chronology = _mapping(document.get("chronology"), "chronology")
    _require_exact_keys(
        chronology,
        {
            "implementation_commit",
            "implementation_tree",
            "working_tree_clean_at_code_commit",
            "satellites_propagated_or_ranked_before_freeze",
            "odd_iq_opened_before_freeze",
            "odd_responses_opened_before_freeze",
        },
        "chronology",
    )
    if (
        any(
            chronology.get(key) is not False
            for key in (
                "satellites_propagated_or_ranked_before_freeze",
                "odd_iq_opened_before_freeze",
                "odd_responses_opened_before_freeze",
            )
        )
        or chronology.get("working_tree_clean_at_code_commit") is not True
    ):
        raise ValueError("final protocol chronology reports pre-freeze access or dirty code")
    if not re.fullmatch(r"[0-9a-f]{40}", str(chronology.get("implementation_commit"))):
        raise ValueError("implementation commit binding is malformed")
    _validate_git_implementation_commit(
        repository_root,
        commit=str(chronology["implementation_commit"]),
        expected_tree=str(chronology["implementation_tree"]),
    )

    policy = _mapping(document.get("dataset_policy"), "dataset_policy")
    if (
        policy
        != {
            "path": DATASET_POLICY_PATH,
            "sha256": DATASET_POLICY_SHA256,
            "repository_commit": DATASET_POLICY_COMMIT,
            "phase": "POST_FIX",
            "newer_or_unlisted_capture_forbidden": True,
            "pre_fix_forbidden": True,
            "capture_only_3_or_5_msps_forbidden": True,
        }
        or _sha256_tag(repository_root / DATASET_POLICY_PATH) != DATASET_POLICY_SHA256
    ):
        raise ValueError("dataset policy authority drifted")
    _validate_historical_file(
        repository_root,
        commit=DATASET_POLICY_COMMIT,
        relative_path=DATASET_POLICY_PATH,
        expected_sha256=DATASET_POLICY_SHA256,
    )

    selector = _mapping(document.get("selector_v2"), "selector_v2")
    if selector != {
        "path": SELECTOR_PATH,
        "file_sha256": SELECTOR_FILE_SHA256,
        "manifest_digest": SELECTOR_SEMANTIC_DIGEST,
        "selector_protocol_path": SELECTOR_PROTOCOL_PATH,
        "selector_protocol_sha256": SELECTOR_PROTOCOL_SHA256,
        "selector_protocol_commit": SELECTOR_PROTOCOL_COMMIT,
        "capture_count": 10,
        "target_count": TARGET_COUNT,
    }:
        raise ValueError("selector-v2 authority drifted")
    selector_path = repository_root / SELECTOR_PATH
    if _sha256_tag(selector_path) != SELECTOR_FILE_SHA256:
        raise ValueError("selector-v2 bytes drifted")
    if _sha256_tag(repository_root / SELECTOR_PROTOCOL_PATH) != SELECTOR_PROTOCOL_SHA256:
        raise ValueError("selector-v2 protocol bytes drifted")
    _validate_historical_file(
        repository_root,
        commit=SELECTOR_PROTOCOL_COMMIT,
        relative_path=SELECTOR_PROTOCOL_PATH,
        expected_sha256=SELECTOR_PROTOCOL_SHA256,
    )
    selector_document = json.loads(selector_path.read_bytes())
    if selector_document.get("manifest_digest") != SELECTOR_SEMANTIC_DIGEST:
        raise ValueError("selector-v2 semantic digest drifted")
    selected = tuple(
        item for item in selector_document["captures"] if item["status"] == "evaluable"
    )
    if (
        tuple(item["session_id"] for item in selected) != CAPTURE_IDS
        or tuple(item["eligible_target_count"] for item in selected) != TARGET_COUNTS
    ):
        raise ValueError("selector-v2 exact cohort drifted")

    if document.get("upstream_conditioning") != {
        "v1_conditioning_disclosure": (
            "frozen-standard-products-may-use-all-qin-for-source-alias-trajectory-and-epoch"
        ),
        "v2_reuse_rule": ("reuse-exact-v1-source-alias-epoch-continuity-and-even-frame-mask"),
        "frozen_v1_file_sha256": (
            "sha256:860b067a154b6b5ecf3172aa2f18105d4ef753cdb5472bab44cbfe9339662c70"
        ),
        "frozen_v1_semantic_manifest_digest": (
            "sha256:c82a548683cbdfd026420ace9c8b6161ba5b69331682d6c68c1baafd73410b39"
        ),
        "downstream_odd_fit_withheld": True,
        "end_to_end_odd_independent": False,
        "required_claim_qualifier": (
            "conditional on frozen upstream all-Qin acquisition and conditioning"
        ),
    }:
        raise ValueError("upstream all-Qin conditioning disclosure drifted")

    captures = document.get("captures")
    if (
        not isinstance(captures, list)
        or tuple(item.get("session_id") for item in captures) != CAPTURE_IDS
    ):
        raise ValueError("final capture identity/order drifted")
    for binding, source, count in zip(captures, selected, TARGET_COUNTS, strict=True):
        _validate_capture(binding, source=source, expected_count=count)

    _validate_site(document.get("site"), repository_root=repository_root)
    _validate_tle(document.get("tle_authority"), captures=captures)
    _validate_chunks(document.get("authorized_odd_chunks"))
    _validate_estimators_and_scoring(document)
    _validate_association(document.get("association"))
    _validate_calibration(
        document.get("corrected_fixed500"), document.get("calibrated_intervals"), repository_root
    )

    implementation = _mapping(document.get("implementation_sha256"), "implementation_sha256")
    if set(implementation) != _IMPLEMENTATION_KEYS:
        raise ValueError("implementation binding key set drifted")
    for relative, expected in implementation.items():
        if not isinstance(expected, str) or _sha256_tag(repository_root / relative) != expected:
            raise ValueError(f"implementation digest drifted: {relative}")
    if implementation["src/leo/analysis/qam/pilot.py"] != (
        "sha256:bcd1054c496648965fa9f8d0f055dffdc30dd7b9215dc164dd0f9e0a890a2eb6"
    ):
        raise ValueError("historical pilot implementation drifted")

    if document.get("protocol_digest") != canonical_digest(
        {key: value for key, value in document.items() if key != "protocol_digest"}
    ):
        raise ValueError("final protocol canonical digest disagrees")
    return cast(dict[str, Any], document)


def _validate_capture(
    binding: dict[str, Any], *, source: dict[str, Any], expected_count: int
) -> None:
    _require_exact_keys(
        binding,
        {
            "session_id",
            "analysis_run_id",
            "recording_bundle_uri",
            "recording_manifest_sha256",
            "analysis_manifest_uri",
            "analysis_manifest_sha256",
            "episode_id",
            "scope_key",
            "target_count",
            "target_mask_digest",
            "sample_rate_hz",
            "stream_id",
            "physical_radio_id",
            "radio_serial",
            "receiver_id",
            "physical_receiver_id",
            "shared_rate_group_id",
            "edge",
            "first_sample_method",
            "first_sample_earliest_utc_ns",
            "first_sample_estimate_utc_ns",
            "first_sample_latest_utc_ns",
            "applied_if_hz",
            "nominal_lnb_lo_hz",
            "nominal_sky_frequency_hz",
            "tle_snapshot",
            "predecessor_tle_snapshot",
        },
        f"capture {binding.get('session_id')}",
    )
    disposition = source["inherited_v1_disposition"]
    episode = disposition["episode"]
    expected_source = {
        "analysis_run_id": source["analysis_run_id"],
        "recording_bundle_uri": disposition["recording_manifest_uri"],
        "recording_manifest_sha256": source["recording_manifest_sha256"],
        "analysis_manifest_uri": disposition["analysis_manifest_uri"],
        "analysis_manifest_sha256": source["analysis_manifest_sha256"],
        "episode_id": episode["episode_id"],
        "scope_key": episode["scope_key"],
        "target_count": expected_count,
        "target_mask_digest": source["target_mask_digest"],
        "sample_rate_hz": 2_500_000,
    }
    if any(binding.get(key) != value for key, value in expected_source.items()):
        raise ValueError(f"capture artifact/selector binding drifted: {binding.get('session_id')}")
    expected_rf = _EXPECTED_RF_UTC[binding["session_id"]]
    observed_rf = (
        binding.get("stream_id"),
        binding.get("physical_radio_id"),
        binding.get("radio_serial"),
        binding.get("receiver_id"),
        binding.get("physical_receiver_id"),
        binding.get("edge"),
        binding.get("first_sample_earliest_utc_ns"),
        binding.get("first_sample_estimate_utc_ns"),
        binding.get("first_sample_latest_utc_ns"),
        binding.get("applied_if_hz"),
        binding.get("nominal_sky_frequency_hz"),
    )
    if observed_rf != expected_rf or binding.get("shared_rate_group_id") != expected_rf[4]:
        raise ValueError(f"capture UTC/RF/topology binding drifted: {binding['session_id']}")
    if binding.get("nominal_lnb_lo_hz") != 9_750_000_000:
        raise ValueError(f"capture nominal LNB authority drifted: {binding['session_id']}")
    CaptureArtifactAuthorityV1(
        session_id=binding["session_id"],
        recording_manifest_uri=binding["recording_bundle_uri"],
        recording_manifest_sha256=binding["recording_manifest_sha256"],
        analysis_run_id=binding["analysis_run_id"],
        analysis_manifest_uri=binding["analysis_manifest_uri"],
        analysis_manifest_sha256=binding["analysis_manifest_sha256"],
        raw_integrity_attestation_id=disposition["raw_integrity_attestation_id"],
        episode_id=binding["episode_id"],
        scope_key=binding["scope_key"],
        target_mask_digest=binding["target_mask_digest"],
    )
    StreamUtcAuthorityV1(
        session_id=binding["session_id"],
        stream_id=binding["stream_id"],
        timing_method=binding["first_sample_method"],
        sample_rate_hz=binding["sample_rate_hz"],
        first_sample_earliest_utc_ns=binding["first_sample_earliest_utc_ns"],
        first_sample_estimate_utc_ns=binding["first_sample_estimate_utc_ns"],
        first_sample_latest_utc_ns=binding["first_sample_latest_utc_ns"],
    )
    NominalRfAuthorityV1(
        session_id=binding["session_id"],
        stream_id=binding["stream_id"],
        radio_id=binding["physical_radio_id"],
        receiver_id=binding["receiver_id"],
        edge=binding["edge"],
        applied_if_center_hz=binding["applied_if_hz"],
        nominal_lnb_lo_hz=binding["nominal_lnb_lo_hz"],
        nominal_sky_frequency_hz=binding["nominal_sky_frequency_hz"],
        rf_rule="applied-if-center-plus-nominal-lnb-lo",
        random_tuning_applied_settings_authoritative=True,
        receiver_frequency_reference_calibrated=False,
        lnb_offset_or_drift_measured=False,
    )


def _validate_site(value: object, *, repository_root: Path) -> None:
    site = _mapping(value, "site")
    expected = {
        "preset": "spinnaker-sausalito",
        "label": "Spinnaker, Sausalito",
        "latitude_deg": 37.858988,
        "longitude_deg": -122.478103,
        "altitude_m": -29.0,
        "position_uncertainty_m": 50.0,
        "provenance": "OpenStreetMap named node 'The Spinnaker, 100 Spinnaker Drive, Sausalito'",
        "source_path": "src/leo/sky/sites.py",
        "source_sha256": "sha256:17056c8b01759f85583116ca4486b4578550a2a7cd48b6fdc2fa90d155783dd9",
        "authority_level": "reviewed-preset-not-capture-bound",
        "capture_bound_position": False,
        "capture_bound_boresight": False,
        "absolute_secure_norad_permitted": False,
        "topology_path": "deploy/station/gauss-four-path-postreboot-20260816-v1.json",
        "topology_sha256": (
            "sha256:5ec14f15bfe2a6abc52024f41db29b4ab6123209e6c4779a47644b1e70c477ae"
        ),
        "topology_digest": (
            "sha256:1aacfb9c5904b6524cad2e82b52427ba0d884ec8c391af58e6d2f5c92c770431"
        ),
    }
    if (
        site != expected
        or _sha256_tag(repository_root / site["source_path"]) != site["source_sha256"]
        or _sha256_tag(repository_root / site["topology_path"]) != site["topology_sha256"]
    ):
        raise ValueError("site/topology authority drifted")
    ObserverSiteAuthorityV1(
        name=site["preset"],
        latitude_deg=site["latitude_deg"],
        longitude_deg=site["longitude_deg"],
        altitude_m=site["altitude_m"],
        position_uncertainty_m=site["position_uncertainty_m"],
        provenance=site["provenance"],
        source_sha256=site["source_sha256"],
        authority_level=site["authority_level"],
        capture_bound_position=False,
        capture_bound_boresight=False,
        absolute_secure_norad_permitted=False,
    )


def _validate_tle(value: object, *, captures: list[dict[str, Any]]) -> None:
    authority = _mapping(value, "tle_authority")
    _require_exact_keys(
        authority,
        {
            "source",
            "scope",
            "selection_rule",
            "mutable_index_is_execution_dependency",
            "frozen_selection_inventory",
        },
        "tle_authority",
    )
    if (
        authority.get("source") != "space-track"
        or authority.get("scope") != "starlink"
        or authority.get("selection_rule")
        != "latest-immutable-snapshot-retrieved-strictly-before-first-target"
        or authority.get("mutable_index_is_execution_dependency") is not False
    ):
        raise ValueError("TLE authority rule drifted")
    inventory = authority.get("frozen_selection_inventory")
    if not isinstance(inventory, list) or tuple(
        item.get("raw_sha256") for item in inventory
    ) != tuple(_SNAPSHOTS):
        raise ValueError("TLE selection inventory drifted")
    for item in inventory:
        _validate_snapshot(item)
    early = tuple(captures[:5])
    late = tuple(captures[5:])
    for capture in early:
        if (
            capture["tle_snapshot"]["raw_sha256"] != tuple(_SNAPSHOTS)[1]
            or capture["predecessor_tle_snapshot"]["raw_sha256"] != tuple(_SNAPSHOTS)[0]
        ):
            raise ValueError("early capture TLE selection drifted")
    for capture in late:
        if (
            capture["tle_snapshot"]["raw_sha256"] != tuple(_SNAPSHOTS)[2]
            or capture["predecessor_tle_snapshot"]["raw_sha256"] != tuple(_SNAPSHOTS)[1]
        ):
            raise ValueError("late capture TLE selection drifted")
    for capture in captures:
        _validate_snapshot(capture["tle_snapshot"])
        _validate_snapshot(capture["predecessor_tle_snapshot"])


def _validate_snapshot(item: dict[str, Any]) -> None:
    _require_exact_keys(
        item,
        {
            "metadata_sha256",
            "retrieved_at",
            "metadata_path",
            "raw_path",
            "raw_sha256",
            "raw_byte_size",
            "satellite_count",
        },
        "TLE snapshot",
    )
    raw_sha256 = item.get("raw_sha256")
    expected = _SNAPSHOTS.get(raw_sha256 if isinstance(raw_sha256, str) else "")
    if expected is None or (
        item.get("metadata_sha256"),
        item.get("retrieved_at"),
        item.get("metadata_path"),
        item.get("raw_path"),
        item.get("raw_byte_size"),
        item.get("satellite_count"),
    ) != (*expected, 1_752_307, 10_972):
        raise ValueError("immutable legacy TLE snapshot binding drifted")


def _validate_chunks(value: object) -> None:
    if not isinstance(value, list) or len(value) != 11:
        raise ValueError("authorized odd chunk inventory drifted")
    if any(
        not isinstance(item, dict)
        or set(item)
        != {
            "session_id",
            "stream_id",
            "relative_path",
            "sample_start",
            "sample_count",
            "compressed_sha256",
        }
        for item in value
    ):
        raise ValueError("authorized odd chunk key set drifted")
    observed = tuple(
        (
            item.get("session_id"),
            item.get("stream_id"),
            item.get("relative_path"),
            item.get("sample_start"),
            item.get("sample_count"),
            item.get("compressed_sha256"),
        )
        for item in value
    )
    if observed != _EXPECTED_CHUNKS:
        raise ValueError("authorized odd chunk geometry/digest drifted")


def _validate_estimators_and_scoring(document: dict[str, Any]) -> None:
    configs = [item.model_dump(mode="json") for item in DEFAULT_STRICT_PAST_CONFIGS]
    if document.get("strict_past_estimators") != {
        "target_numeric_even_cfo_consumed": False,
        "history_interval": "[target-horizon,target)",
        "configs": configs,
        "configuration_digest": canonical_digest(configs),
        "calibration_name_mapping": {"lean_curvature_500ms": "lean_500ms_quadratic"},
    }:
        raise ValueError("strict-past estimator design drifted")
    if document.get("odd_response") != {
        "qin_symbols": "zero-based-odd-1-through-299",
        "acquisition_center": "inherited-alias-trajectory",
        "target_numeric_even_cfo_consumed": False,
        "residual_half_width_hz": 2000.0,
        "minimum_exact_coherence": 0.02,
        "minimum_coherence_margin": 0.0,
        "statuses_retained": ["finite", "boundary", "no_support", "missing"],
        "accuracy_mask": "finite-and-eligible-only",
        "membership_mutation_permitted": False,
    }:
        raise ValueError("odd-only response design drifted")
    scoring = document.get("scoring")
    expected_gate = {
        "maximum_equal_capture_rms_ratio": 0.95,
        "minimum_capture_wins_out_of_10": 8,
        "maximum_any_capture_ratio": 1.10,
        "maximum_completion_difference_percentage_points": 1.0,
        "all_10_capture_comparisons_required": True,
        "minimum_per_capture_response_eligible_fraction": 0.5,
        "minimum_per_capture_common_accuracy_fraction": 0.5,
        "missing_capture_is_failure": True,
    }
    if scoring != {
        "primary_metric": (
            "equal-capture downstream-withheld odd-Qin CFO RMS Hz on common eligible mask, "
            "conditional on frozen upstream all-Qin acquisition and conditioning"
        ),
        "identical_denominator_target_count": TARGET_COUNT,
        "common_mask_requires_all_four_predictions_complete": True,
        "boundary_no_support_missing_retained_in_denominator": True,
        "quadratic_promotion_gate": expected_gate,
    }:
        raise ValueError("holdout scoring/availability design drifted")


def _validate_association(value: object) -> None:
    association = _mapping(value, "association")
    required = {
        "catalog_scope": "Starlink-only",
        "time_shift_s": 0.0,
        "primary_lane": "lean_500ms_quadratic",
        "baseline_lane": "fixed_500ms_linear",
        "bin_width_ms": 20.0,
        "training_fraction_of_full_target_span": 0.6,
        "maximum_pre_response_compute_seconds": 3600.0,
        "minimum_total_bins": 10,
        "minimum_training_bins": 6,
        "minimum_evaluation_bins": 4,
        "minimum_visible_candidates": 2,
        "nuisance_primary": "one-constant-CFO-offset-per-capture",
        "free_candidate_rate_primary": False,
        "shared_rate_diagnostic_only": True,
        "shared_rate_group": "physical_receiver_id",
        "shared_rate_prior_sigma_hz_s": 50.0,
        "shared_rate_hard_bound_hz_s": 150.0,
        "shared_rate_objective": (
            "(sum_capture_training_MSE + 50^2*sum_group(rate/50)^2)/capture_count"
        ),
        "wrong_time_offsets_s": [float(value) for value in range(-18000, 0, 900)]
        + [float(value) for value in range(900, 18001, 900)],
        "within_track_permutations": 20,
        "within_track_permutation_seed": 20260826,
        "rolling_origin_training_fractions": [0.4, 0.6, 0.8],
        "minimum_claim_heldout_odd_bins": 8,
        "minimum_heldout_odd_bin_fraction": 0.5,
        "maximum_claim_rank_one_heldout_odd_rms_hz": 100.0,
        "training_runner_margin_ratio_minimum": 1.10,
        "heldout_runner_margin_ratio_minimum": 1.10,
        "wrong_time_minimum_scored": 38,
        "null_empirical_p_maximum": 0.05,
        "all_20_permutations_required": True,
        "minimum_stable_rolling_origins": 2,
        "primary_baseline_rank_one_agreement_required": True,
        "utc_site_predecessor_identity_stability_required": True,
        "absolute_secure_norad_forced_false": True,
    }
    site_controls = association.get("site_sensitivity")
    non_site = {key: item for key, item in association.items() if key != "site_sensitivity"}
    latitude_delta = 50.0 / 111_320.0
    longitude_delta = 50.0 / (111_320.0 * math.cos(math.radians(37.858988)))
    expected_sites = [
        {
            "control_id": "site-north-50m",
            "latitude_deg": 37.858988 + latitude_delta,
            "longitude_deg": -122.478103,
            "altitude_m": -29.0,
            "label": "Spinnaker, Sausalito north 50 m sensitivity",
        },
        {
            "control_id": "site-south-50m",
            "latitude_deg": 37.858988 - latitude_delta,
            "longitude_deg": -122.478103,
            "altitude_m": -29.0,
            "label": "Spinnaker, Sausalito south 50 m sensitivity",
        },
        {
            "control_id": "site-east-50m",
            "latitude_deg": 37.858988,
            "longitude_deg": -122.478103 + longitude_delta,
            "altitude_m": -29.0,
            "label": "Spinnaker, Sausalito east 50 m sensitivity",
        },
        {
            "control_id": "site-west-50m",
            "latitude_deg": 37.858988,
            "longitude_deg": -122.478103 - longitude_delta,
            "altitude_m": -29.0,
            "label": "Spinnaker, Sausalito west 50 m sensitivity",
        },
    ]
    if non_site != required or site_controls != expected_sites:
        raise ValueError("final association/control design drifted")


def _validate_calibration(fixed: object, intervals: object, repository_root: Path) -> None:
    if (
        fixed
        != {
            "publication_commit": "ded4f27",
            "execution_authority_commit": "bf0548e",
            "metrics_path": "reports/figures/2026_08_26_fixed500_calibration/metrics.json",
            "metrics_sha256": (
                "sha256:b0d832c9125b40a6bc23e0d13b135e8804a83dc367ffa963eb355d94977c03ac"
            ),
            "fixed500_point_rmse_hz_s": 291.5921,
            "strict_past_quadratic_rmse_hz_s": 35.8038,
            "fixed500_point_gate": "fail",
        }
        or _sha256_tag(repository_root / fixed["metrics_path"]) != fixed["metrics_sha256"]
    ):
        raise ValueError("corrected fixed500 binding drifted")
    if intervals != {
        "formal_95pct_status": "abstain",
        "reason": "requested-order-exceeds-12-calibration-groups",
        "descriptive_grouped_multiplier": 25.725265,
        "descriptive_median_halfwidth_hz_s": 501.144,
        "descriptive_values_are_not_formal_coverage": True,
    }:
        raise ValueError("calibrated interval abstention drifted")


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object")
    return cast(dict[str, Any], value)


def _sha256_tag(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def _load_json_without_duplicate_keys(path: Path) -> object:
    def reject_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def _require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} key set drifted")


def _validate_git_implementation_commit(
    repository_root: Path,
    *,
    commit: str,
    expected_tree: str,
) -> None:
    if not re.fullmatch(r"[0-9a-f]{40}", expected_tree):
        raise ValueError("implementation tree binding is malformed")
    try:
        resolved_commit = subprocess.run(
            ["git", "rev-parse", f"{commit}^{{commit}}"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        resolved_tree = subprocess.run(
            ["git", "rev-parse", f"{commit}^{{tree}}"],
            cwd=repository_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError("implementation commit is unavailable") from error
    if resolved_commit != commit or resolved_tree != expected_tree:
        raise ValueError("implementation commit/tree binding drifted")
    try:
        tree_diff = subprocess.run(
            [
                "git",
                "diff",
                "--quiet",
                commit,
                "--",
                "src/leo",
                "tools/run_final_doppler_holdout.py",
                "uv.lock",
            ],
            cwd=repository_root,
            check=False,
        )
    except OSError as error:
        raise ValueError("implementation tree comparison is unavailable") from error
    if tree_diff.returncode != 0:
        raise ValueError("execution source tree differs from the frozen implementation commit")
    for relative in _IMPLEMENTATION_KEYS:
        try:
            current = subprocess.run(
                ["git", "hash-object", relative],
                cwd=repository_root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            committed = subprocess.run(
                ["git", "rev-parse", f"{commit}:{relative}"],
                cwd=repository_root,
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError) as error:
            raise ValueError(f"implementation path is unavailable: {relative}") from error
        if current != committed:
            raise ValueError(f"implementation path is not from the frozen commit: {relative}")


def _validate_historical_file(
    repository_root: Path,
    *,
    commit: str,
    relative_path: str,
    expected_sha256: str,
) -> None:
    try:
        payload = subprocess.run(
            ["git", "show", f"{commit}:{relative_path}"],
            cwd=repository_root,
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(f"historical authority is unavailable: {relative_path}") from error
    if "sha256:" + hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError(f"historical authority digest drifted: {relative_path}")
