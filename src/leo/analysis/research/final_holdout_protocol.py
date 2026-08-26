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

SCHEMA_V1 = "org.leo.research.final-doppler-holdout-satellite/v1"
SCHEMA_V2 = "org.leo.research.final-doppler-holdout-satellite/v2"
SCHEMA_V3 = "org.leo.research.final-doppler-holdout-satellite/v3"
SCHEMA = SCHEMA_V1
BASE_PROTOCOL_PATH = "config/analysis/final-doppler-holdout-satellite-protocol-v1.json"
BASE_PROTOCOL_SHA256 = "sha256:8e5a62993fe2e25496cb838d3ec866fe8ccf6fbca1f6ca122e312fd32c6af58b"
BASE_PROTOCOL_DIGEST = "sha256:df7e1f41e2e339af3d46773b4172a97304f518573fc55ddc4a2746a00f883a31"
BASE_PROTOCOL_COMMIT = "19d9da26939750d5e07898d94ed860bbe2ba0924"
FAILURE_EVIDENCE_COMMIT = "94e9c8b6d765e01da228705c1c167eb2398cab30"
FAILURE_EVIDENCE_TREE = "e199a7b5b042aa44f896c707188f192ce89583b6"
FAILURE_AMENDMENT_PATH = (
    "config/analysis/final-doppler-holdout-satellite-protocol-v1-amendment-001.json"
)
FAILURE_AMENDMENT_SHA256 = "sha256:3df8649c0b58e0286877370c965d28d7456aa216606c78093ea35c3ffae88bca"
FAILURE_AMENDMENT_DIGEST = "sha256:03b273bb806c98c4ee7e6e89907af0ba7c58c2650e9698a84878ac1ddca494e2"
FAILURE_RECEIPT_PATH = (
    "reports/figures/2026_08_26_final_doppler_holdout_failed_attempt1/"
    "attempt-1-failure-receipt.json"
)
FAILURE_RECEIPT_SHA256 = "sha256:996b9a428847beb582d33c23e85ec3e7813ec56c640441a300ef20a85c2035ed"
FAILURE_RECEIPT_DIGEST = "sha256:d16f2af3d1e463eb1d5814d36927759037e0bc7d68442704411f3bfa8ec1b2a3"
FAILURE_COMBINED_OUTPUT_PATH = (
    "reports/figures/2026_08_26_final_doppler_holdout_failed_attempt1/attempt-1-command-output.log"
)
FAILURE_COMBINED_OUTPUT_SHA256 = (
    "sha256:73efe2478a83ed2e42e97884a7daa6def98782cc2ed12d0b0b397b83f40db408"
)
ATTEMPT_1_PREDICTION_PATH = (
    "reports/figures/2026_08_26_final_doppler_holdout_failed_attempt1/prediction-ledger.json"
)
ATTEMPT_1_PREDICTION_SHA256 = (
    "sha256:7aee33ebb11b12bc2d15d228b556c5f92fd0c80c7bad76abfac6a6ba95be8978"
)
ATTEMPT_1_PREDICTION_DIGEST = (
    "sha256:b6a1db7f3785eac1dd40fa6c75a90e4ced6e36730a0adedd3e7aeeb20feeeca8"
)
ATTEMPT_1_BINS_PATH = (
    "reports/figures/2026_08_26_final_doppler_holdout_failed_attempt1/"
    "association-bin-inventory.json"
)
ATTEMPT_1_BINS_SHA256 = "sha256:cc7e64e22eba73e5f8495ba375ecfbe96bbf842fdcde17b7f5c1fdd1ae16d26a"
ATTEMPT_1_BINS_DIGEST = "sha256:ce4763244430d0a46eb1184d9c573b3fab0e6cc529c1287a7d0ea098e481857e"
CORRECTED_BINS_SHA256 = "sha256:81c909befea20f8291e5e6606e9fe48c8889e051283a4a8051c29c1ab05d7d1e"
CORRECTED_BINS_DIGEST = "sha256:a01e53e917ea33295273778f23412629b83c78ee63ef4c8eafcd761e8f2d5c53"
V2_PROTOCOL_PATH = "config/analysis/final-doppler-holdout-satellite-protocol-v2.json"
V2_PROTOCOL_SHA256 = "sha256:529ca7dd76aabb5b02e63b57112893db62e8f3c6d0dfab5afe76af3fa6035532"
V2_PROTOCOL_DIGEST = "sha256:f781d18cb2917b6cfd01fe0d72f9db62b80a36d6f6979ca525c55c45b718f86d"
V2_PROTOCOL_COMMIT = "baf5f3f874fd4827883fe9578577ecf57bc3b2da"
V2_PROTOCOL_TREE = "9abca3d9ed602855e61fb662083f1497b5e0c71d"
PRE_RESPONSE_FREEZE_COMMIT = "5f255659b284f631639ff6bfef0ffad6cb4bfe31"
PRE_RESPONSE_FREEZE_TREE = "ca3adf831c503e853013f366ff99f089925e7a7a"
PRE_RESPONSE_DIRECTORY = "reports/figures/2026_08_26_final_doppler_holdout_attempt2"
PRE_RESPONSE_PREDICTION_PATH = f"{PRE_RESPONSE_DIRECTORY}/prediction-ledger.json"
PRE_RESPONSE_PREDICTION_SHA256 = ATTEMPT_1_PREDICTION_SHA256
PRE_RESPONSE_PREDICTION_DIGEST = ATTEMPT_1_PREDICTION_DIGEST
PRE_RESPONSE_BINS_PATH = f"{PRE_RESPONSE_DIRECTORY}/association-bin-inventory.json"
PRE_RESPONSE_BINS_SHA256 = CORRECTED_BINS_SHA256
PRE_RESPONSE_BINS_DIGEST = CORRECTED_BINS_DIGEST
PRE_RESPONSE_RANKINGS_PATH = f"{PRE_RESPONSE_DIRECTORY}/pre-response-rankings.json"
PRE_RESPONSE_RANKINGS_SHA256 = (
    "sha256:fbc9248c41cc6f64f9e8c51a8fcd36987a07ba1d44b25909700da54542f18094"
)
PRE_RESPONSE_RANKINGS_DIGEST = (
    "sha256:31115cc456c791686d240528ce65d9f0a4b923dddcabebaa1a67c9ff1cd44242"
)
PRE_RESPONSE_RECEIPT_PATH = f"{PRE_RESPONSE_DIRECTORY}/pre-response-receipt.json"
PRE_RESPONSE_RECEIPT_SHA256 = (
    "sha256:420cad03d0c7bbd35169fd5b98c877323ea87b9499244fc4e2f9a42e020a994d"
)
PRE_RESPONSE_RECEIPT_DIGEST = (
    "sha256:68919074a4e10cfc0780197d17904f063b7aac6a84c0aee427996cbdf29f6039"
)
PRE_RESPONSE_PACKAGE_MANIFEST_PATH = (
    f"{PRE_RESPONSE_DIRECTORY}/pre-response-packaging-manifest.json"
)
PRE_RESPONSE_PACKAGE_MANIFEST_SHA256 = (
    "sha256:6bb02d00e1f8712e0ddb55d774466b4ba001fc7f13154430c7596e88e3568880"
)
PRE_RESPONSE_PACKAGE_MANIFEST_DIGEST = (
    "sha256:8cf3811b9b24becb82a49073bdf2f0f8dc58d04f53dc9fad13bd2db813583fd6"
)
PRE_RESPONSE_RANKINGS_PACKAGE_PATH = f"{PRE_RESPONSE_DIRECTORY}/pre-response-rankings.json.zst"
PRE_RESPONSE_RANKINGS_PACKAGE_SHA256 = (
    "sha256:b8cca43df3fe6994055230c885b36167e82efa2710cf2a4fbeb77f56c6a59f65"
)
ATTACH_FAILURE_EVIDENCE_COMMIT = "388bd30e6bb55bbd49895f12f9c2e21f4efa3507"
ATTACH_FAILURE_EVIDENCE_TREE = "dc9328dcbe6fa11d618ecbbf868e8333199d50cc"
ATTACH_FAILURE_RECEIPT_PATH = (
    "reports/figures/2026_08_26_final_doppler_holdout_attempt2_odd_attachment/"
    "attach-attempt-1-failure-receipt.json"
)
ATTACH_FAILURE_RECEIPT_SHA256 = (
    "sha256:8b0fece5fcb690c210d482843854e311993eef47c46f25b8ba945904d1a63e00"
)
ATTACH_FAILURE_RECEIPT_DIGEST = (
    "sha256:ea02d448c38d4816e786942d4e2fad3a97d52ee56b9c0eda5a964d7bac71593c"
)
ATTACH_FAILURE_OUTPUT_PATH = (
    "reports/figures/2026_08_26_final_doppler_holdout_attempt2-attach-odd-command-output.log"
)
ATTACH_FAILURE_OUTPUT_SHA256 = (
    "sha256:34aa86d412f25be882f9f4ccd3f8b16e2185493a730ba353340a24c3ad36ad3c"
)
ATTACH_AMENDMENT_PATH = (
    "config/analysis/final-doppler-holdout-satellite-protocol-v2-amendment-001.json"
)
ATTACH_AMENDMENT_SHA256 = "sha256:7ed355990579ea900a83b76e4e272892d6b90577bee1ca6731490a078f69f38b"
ATTACH_AMENDMENT_DIGEST = "sha256:cb9f0233fb1ba817b30bf42f08afa2668e81a001553103f5f8da5710a34d3d18"
ATTACH_AMENDMENT_COMMIT = "fe6dd1e0dd51775e2986d8845032327376eea77c"
ATTACH_AMENDMENT_TREE = "558526eaf8f88b919eb8ac599c609bd6e1ba3a07"
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

_EXPECTED_CHUNKS_V1_V2 = (
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
_REMOVED_UNUSED_CHUNK = _EXPECTED_CHUNKS_V1_V2[-2]
_EXPECTED_CHUNKS_V3 = tuple(
    item for item in _EXPECTED_CHUNKS_V1_V2 if item != _REMOVED_UNUSED_CHUNK
)
# Retained for historical tests and external audit helpers that named the v1/v2
# inventory before v3 existed.
_EXPECTED_CHUNKS = _EXPECTED_CHUNKS_V1_V2
V2_CHUNK_INVENTORY_DIGEST = (
    "sha256:f86a9cf8177d22ba6cf8507a24d9cdc723c2325dc97c34eabded642ebda2111e"
)
V3_CHUNK_INVENTORY_DIGEST = (
    "sha256:ff8a776f7f07f17bede7ab2fcb7e8cfa0e144771c571380db7a2b690c195a4cb"
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
_TOP_LEVEL_KEYS_V2 = _TOP_LEVEL_KEYS | {"supersession"}
_TOP_LEVEL_KEYS_V3 = _TOP_LEVEL_KEYS_V2 | {"attachment_correction"}
_SCIENTIFIC_KEYS = {
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
}


def load_and_validate_historical_final_protocol_v1(
    path: Path,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Verify retired v1 against its historical implementation, never execute it."""

    return _load_and_validate_protocol_v1(
        path,
        repository_root=repository_root,
        require_current_implementation=False,
    )


def _load_and_validate_protocol_v1(
    path: Path,
    *,
    repository_root: Path,
    require_current_implementation: bool,
) -> dict[str, Any]:
    """Load v1 with either historical or now-retired execution semantics."""

    document = _load_json_without_duplicate_keys(path)
    if not isinstance(document, dict) or document.get("schema") != SCHEMA_V1:
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
        require_current_source=require_current_implementation,
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
        observed = (
            _sha256_tag(repository_root / relative)
            if require_current_implementation
            else _sha256_tag_at_commit(
                repository_root,
                commit=str(chronology["implementation_commit"]),
                relative_path=relative,
            )
        )
        if not isinstance(expected, str) or observed != expected:
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


def load_and_validate_historical_final_protocol_v2(
    path: Path,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Verify retired v2 against its historical implementation, never execute it."""

    return _load_and_validate_protocol_v2(
        path,
        repository_root=repository_root,
        require_current_implementation=False,
    )


def _load_and_validate_protocol_v2(
    path: Path,
    *,
    repository_root: Path,
    require_current_implementation: bool,
) -> dict[str, Any]:
    """Load v2 with historical or now-retired execution semantics."""

    document = _load_json_without_duplicate_keys(path)
    if not isinstance(document, dict) or document.get("schema") != SCHEMA_V2:
        raise ValueError("unsupported final holdout protocol")
    _require_exact_keys(document, _TOP_LEVEL_KEYS_V2, "protocol v2")
    if document.get("status") != "frozen_after_attempt_1_failure_before_corrected_rerun":
        raise ValueError("final holdout v2 chronology is not frozen")
    chronology = _mapping(document.get("chronology"), "chronology")
    _require_exact_keys(
        chronology,
        {
            "implementation_commit",
            "implementation_tree",
            "working_tree_clean_at_code_commit",
            "base_v1_frozen_before_attempt_1",
            "attempt_1_candidate_propagation_or_ranking_occurred",
            "attempt_1_candidate_results_printed_or_inspected",
            "odd_iq_opened_before_v2_freeze",
            "odd_responses_opened_before_v2_freeze",
            "correction_chosen_without_candidate_results_or_odd_responses",
            "corrected_candidate_propagation_or_ranking_before_v2_freeze",
        },
        "chronology v2",
    )
    expected_flags = {
        "working_tree_clean_at_code_commit": True,
        "base_v1_frozen_before_attempt_1": True,
        "attempt_1_candidate_propagation_or_ranking_occurred": True,
        "attempt_1_candidate_results_printed_or_inspected": False,
        "odd_iq_opened_before_v2_freeze": False,
        "odd_responses_opened_before_v2_freeze": False,
        "correction_chosen_without_candidate_results_or_odd_responses": True,
        "corrected_candidate_propagation_or_ranking_before_v2_freeze": False,
    }
    if any(chronology.get(key) is not value for key, value in expected_flags.items()):
        raise ValueError("final holdout v2 chronology flags drifted")
    commit = str(chronology.get("implementation_commit"))
    tree = str(chronology.get("implementation_tree"))
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("implementation commit binding is malformed")
    _validate_git_implementation_commit(
        repository_root,
        commit=commit,
        expected_tree=tree,
        require_current_source=require_current_implementation,
    )

    base_path = repository_root / BASE_PROTOCOL_PATH
    if _sha256_tag(base_path) != BASE_PROTOCOL_SHA256:
        raise ValueError("retired v1 protocol bytes drifted")
    base = load_and_validate_historical_final_protocol_v1(
        base_path,
        repository_root=repository_root,
    )
    if base["protocol_digest"] != BASE_PROTOCOL_DIGEST:
        raise ValueError("retired v1 protocol digest drifted")
    for key in _SCIENTIFIC_KEYS:
        if document.get(key) != base.get(key):
            raise ValueError(f"v2 scientific field differs from frozen v1: {key}")
    _validate_supersession_v2(document.get("supersession"), repository_root=repository_root)

    implementation = _mapping(document.get("implementation_sha256"), "implementation_sha256")
    if set(implementation) != _IMPLEMENTATION_KEYS:
        raise ValueError("implementation binding key set drifted")
    for relative, expected in implementation.items():
        observed = (
            _sha256_tag(repository_root / relative)
            if require_current_implementation
            else _sha256_tag_at_commit(
                repository_root,
                commit=commit,
                relative_path=relative,
            )
        )
        if not isinstance(expected, str) or observed != expected:
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


def load_and_validate_final_protocol(path: Path, *, repository_root: Path) -> dict[str, Any]:
    """Load only active v3; verify retired v1/v2 before rejecting execution."""

    document = _load_json_without_duplicate_keys(path)
    if not isinstance(document, dict):
        raise ValueError("unsupported final holdout protocol")
    schema = document.get("schema")
    if schema == SCHEMA_V1:
        load_and_validate_historical_final_protocol_v1(
            path,
            repository_root=repository_root,
        )
        raise ValueError("final holdout protocol v1 is retired after failed attempt 1")
    if schema == SCHEMA_V2:
        load_and_validate_historical_final_protocol_v2(
            path,
            repository_root=repository_root,
        )
        raise ValueError("final holdout protocol v2 attachment authority is retired")
    if schema != SCHEMA_V3:
        raise ValueError("unsupported final holdout protocol")
    return _load_and_validate_protocol_v3(path, repository_root=repository_root)


def _load_and_validate_protocol_v3(
    path: Path,
    *,
    repository_root: Path,
) -> dict[str, Any]:
    """Validate the response-only v3 authority and its exact historical bridge."""

    document = _load_json_without_duplicate_keys(path)
    if not isinstance(document, dict) or document.get("schema") != SCHEMA_V3:
        raise ValueError("unsupported final holdout protocol")
    _require_exact_keys(document, _TOP_LEVEL_KEYS_V3, "protocol v3")
    if document.get("status") != "frozen_response_authority_after_attach_attempt_1_failure":
        raise ValueError("final holdout v3 chronology is not frozen")
    chronology = _mapping(document.get("chronology"), "chronology v3")
    _require_exact_keys(
        chronology,
        {
            "implementation_commit",
            "implementation_tree",
            "working_tree_clean_at_code_commit",
            "v1_and_v2_execution_retired",
            "pre_response_artifacts_generated_under_v2",
            "pre_response_candidate_results_inspected_before_v3",
            "pre_response_candidate_propagation_or_ranking_rerun_before_v3",
            "attach_attempt_1_failed_before_iq_or_odd_measurement",
            "odd_iq_opened_before_v3_freeze",
            "odd_responses_opened_before_v3_freeze",
            "chunk_correction_chosen_without_odd_iq_or_responses",
        },
        "chronology v3",
    )
    expected_flags = {
        "working_tree_clean_at_code_commit": True,
        "v1_and_v2_execution_retired": True,
        "pre_response_artifacts_generated_under_v2": True,
        "pre_response_candidate_results_inspected_before_v3": True,
        "pre_response_candidate_propagation_or_ranking_rerun_before_v3": False,
        "attach_attempt_1_failed_before_iq_or_odd_measurement": True,
        "odd_iq_opened_before_v3_freeze": False,
        "odd_responses_opened_before_v3_freeze": False,
        "chunk_correction_chosen_without_odd_iq_or_responses": True,
    }
    if any(chronology.get(key) is not value for key, value in expected_flags.items()):
        raise ValueError("final holdout v3 chronology flags drifted")
    commit = str(chronology.get("implementation_commit"))
    tree = str(chronology.get("implementation_tree"))
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("implementation commit binding is malformed")
    _validate_git_implementation_commit(
        repository_root,
        commit=commit,
        expected_tree=tree,
        require_current_source=True,
    )

    v2_path = repository_root / V2_PROTOCOL_PATH
    if _sha256_tag(v2_path) != V2_PROTOCOL_SHA256:
        raise ValueError("retired v2 protocol bytes drifted")
    v2 = load_and_validate_historical_final_protocol_v2(
        v2_path,
        repository_root=repository_root,
    )
    if v2["protocol_digest"] != V2_PROTOCOL_DIGEST:
        raise ValueError("retired v2 protocol digest drifted")
    changed_keys = {
        "schema",
        "status",
        "chronology",
        "authorized_odd_chunks",
        "implementation_sha256",
        "protocol_digest",
        "attachment_correction",
    }
    for key in _TOP_LEVEL_KEYS_V3 - changed_keys:
        if document.get(key) != v2.get(key):
            raise ValueError(f"v3 non-chunk field differs from frozen v2: {key}")
    _validate_chunks(
        document.get("authorized_odd_chunks"),
        expected=_EXPECTED_CHUNKS_V3,
    )
    if canonical_digest(document["authorized_odd_chunks"]) != V3_CHUNK_INVENTORY_DIGEST:
        raise ValueError("v3 authorized odd chunk digest drifted")
    _validate_attachment_correction_v3(
        document.get("attachment_correction"),
        repository_root=repository_root,
    )

    implementation = _mapping(document.get("implementation_sha256"), "implementation_sha256")
    if set(implementation) != _IMPLEMENTATION_KEYS:
        raise ValueError("implementation binding key set drifted")
    permitted_source_changes = {
        "src/leo/analysis/research/doppler_holdout_odd_adapter.py",
        "src/leo/analysis/research/final_holdout_protocol.py",
        "tools/run_final_doppler_holdout.py",
    }
    for relative, expected in implementation.items():
        if not isinstance(expected, str) or _sha256_tag(repository_root / relative) != expected:
            raise ValueError(f"implementation digest drifted: {relative}")
        if (
            relative not in permitted_source_changes
            and expected != v2["implementation_sha256"][relative]
        ):
            raise ValueError(f"v3 changed non-bridge implementation: {relative}")
    if implementation["src/leo/analysis/qam/pilot.py"] != (
        "sha256:bcd1054c496648965fa9f8d0f055dffdc30dd7b9215dc164dd0f9e0a890a2eb6"
    ):
        raise ValueError("historical pilot implementation drifted")
    if document.get("protocol_digest") != canonical_digest(
        {key: value for key, value in document.items() if key != "protocol_digest"}
    ):
        raise ValueError("final protocol canonical digest disagrees")
    return cast(dict[str, Any], document)


def _expected_attachment_correction_v3() -> dict[str, Any]:
    """Return the exact response-free v3 bridge/correction authority."""

    removed = {
        "session_id": _REMOVED_UNUSED_CHUNK[0],
        "stream_id": _REMOVED_UNUSED_CHUNK[1],
        "relative_path": _REMOVED_UNUSED_CHUNK[2],
        "sample_start": _REMOVED_UNUSED_CHUNK[3],
        "sample_count": _REMOVED_UNUSED_CHUNK[4],
        "compressed_sha256": _REMOVED_UNUSED_CHUNK[5],
    }
    return {
        "historical_v2_protocol": {
            "path": V2_PROTOCOL_PATH,
            "commit": V2_PROTOCOL_COMMIT,
            "tree": V2_PROTOCOL_TREE,
            "sha256": V2_PROTOCOL_SHA256,
            "semantic_digest": V2_PROTOCOL_DIGEST,
            "execution_retired": True,
            "pre_response_authority_only": True,
        },
        "pre_response_bridge": {
            "freeze_commit": PRE_RESPONSE_FREEZE_COMMIT,
            "freeze_tree": PRE_RESPONSE_FREEZE_TREE,
            "prediction_ledger_path": PRE_RESPONSE_PREDICTION_PATH,
            "prediction_ledger_sha256": PRE_RESPONSE_PREDICTION_SHA256,
            "prediction_ledger_digest": PRE_RESPONSE_PREDICTION_DIGEST,
            "association_bins_path": PRE_RESPONSE_BINS_PATH,
            "association_bins_sha256": PRE_RESPONSE_BINS_SHA256,
            "association_bins_digest": PRE_RESPONSE_BINS_DIGEST,
            "rankings_raw_path": PRE_RESPONSE_RANKINGS_PATH,
            "rankings_raw_sha256": PRE_RESPONSE_RANKINGS_SHA256,
            "rankings_raw_digest": PRE_RESPONSE_RANKINGS_DIGEST,
            "pre_response_receipt_path": PRE_RESPONSE_RECEIPT_PATH,
            "pre_response_receipt_sha256": PRE_RESPONSE_RECEIPT_SHA256,
            "pre_response_receipt_digest": PRE_RESPONSE_RECEIPT_DIGEST,
            "package_manifest_path": PRE_RESPONSE_PACKAGE_MANIFEST_PATH,
            "package_manifest_sha256": PRE_RESPONSE_PACKAGE_MANIFEST_SHA256,
            "package_manifest_digest": PRE_RESPONSE_PACKAGE_MANIFEST_DIGEST,
            "rankings_package_path": PRE_RESPONSE_RANKINGS_PACKAGE_PATH,
            "rankings_package_sha256": PRE_RESPONSE_RANKINGS_PACKAGE_SHA256,
            "all_pre_response_artifacts_byte_identical": True,
            "pre_response_recomputation_permitted": False,
        },
        "failed_attachment": {
            "evidence_commit": ATTACH_FAILURE_EVIDENCE_COMMIT,
            "evidence_tree": ATTACH_FAILURE_EVIDENCE_TREE,
            "failure_receipt_path": ATTACH_FAILURE_RECEIPT_PATH,
            "failure_receipt_sha256": ATTACH_FAILURE_RECEIPT_SHA256,
            "failure_receipt_digest": ATTACH_FAILURE_RECEIPT_DIGEST,
            "combined_command_output_path": ATTACH_FAILURE_OUTPUT_PATH,
            "combined_command_output_sha256": ATTACH_FAILURE_OUTPUT_SHA256,
            "status": "failed_closed_before_odd_measurement",
            "recording_store_opened": True,
            "recording_store_inspect_call_count": 0,
            "recording_store_reader_call_count": 0,
            "recording_reader_read_call_count": 0,
            "iq_byte_count": 0,
            "odd_measurement_count": 0,
            "attachment_or_receipt_written": False,
        },
        "retirement_amendment": {
            "path": ATTACH_AMENDMENT_PATH,
            "commit": ATTACH_AMENDMENT_COMMIT,
            "tree": ATTACH_AMENDMENT_TREE,
            "sha256": ATTACH_AMENDMENT_SHA256,
            "semantic_digest": ATTACH_AMENDMENT_DIGEST,
        },
        "chunk_authority_correction": {
            "original_chunk_count": 11,
            "original_chunk_inventory_digest": V2_CHUNK_INVENTORY_DIGEST,
            "active_chunk_count": 10,
            "active_chunk_inventory_digest": V3_CHUNK_INVENTORY_DIGEST,
            "removed_chunk": removed,
            "removed_chunk_guarded_window_use_count": 0,
            "target_count": TARGET_COUNT,
            "guarded_window_coverage_failures": 0,
            "all_retained_chunks_used": True,
            "unused_chunk_fail_closed_guard_retained": True,
            "pre_storage_sufficiency_and_minimality_preflight_required": True,
            "reader_and_estimator_implementation_unchanged": True,
            "new_iq_or_odd_response_evidence_used": False,
        },
        "execution": {
            "predict_permitted": False,
            "attach_odd_permitted": True,
            "report_permitted": True,
            "historical_v2_verifies_pre_response_only": True,
            "active_v3_supplies_response_authority_only": True,
            "successful_attachment_receipt_schema": (
                "org.leo.research.final-holdout-odd-attachment-receipt/v2"
            ),
        },
    }


def _validate_attachment_correction_v3(value: object, *, repository_root: Path) -> None:
    correction = _mapping(value, "attachment_correction")
    if correction != _expected_attachment_correction_v3():
        raise ValueError("final holdout v3 attachment correction authority drifted")

    current_files = (
        (V2_PROTOCOL_PATH, V2_PROTOCOL_SHA256),
        (PRE_RESPONSE_PREDICTION_PATH, PRE_RESPONSE_PREDICTION_SHA256),
        (PRE_RESPONSE_BINS_PATH, PRE_RESPONSE_BINS_SHA256),
        (PRE_RESPONSE_RECEIPT_PATH, PRE_RESPONSE_RECEIPT_SHA256),
        (PRE_RESPONSE_PACKAGE_MANIFEST_PATH, PRE_RESPONSE_PACKAGE_MANIFEST_SHA256),
        (PRE_RESPONSE_RANKINGS_PACKAGE_PATH, PRE_RESPONSE_RANKINGS_PACKAGE_SHA256),
        (ATTACH_FAILURE_RECEIPT_PATH, ATTACH_FAILURE_RECEIPT_SHA256),
        (ATTACH_FAILURE_OUTPUT_PATH, ATTACH_FAILURE_OUTPUT_SHA256),
        (ATTACH_AMENDMENT_PATH, ATTACH_AMENDMENT_SHA256),
    )
    for relative, digest in current_files:
        if _sha256_tag(repository_root / relative) != digest:
            raise ValueError(f"final holdout v3 correction bytes drifted: {relative}")
    _validate_git_implementation_commit(
        repository_root,
        commit=V2_PROTOCOL_COMMIT,
        expected_tree=V2_PROTOCOL_TREE,
        require_current_source=False,
    )
    _validate_git_implementation_commit(
        repository_root,
        commit=PRE_RESPONSE_FREEZE_COMMIT,
        expected_tree=PRE_RESPONSE_FREEZE_TREE,
        require_current_source=False,
    )
    _validate_git_implementation_commit(
        repository_root,
        commit=ATTACH_FAILURE_EVIDENCE_COMMIT,
        expected_tree=ATTACH_FAILURE_EVIDENCE_TREE,
        require_current_source=False,
    )
    _validate_git_implementation_commit(
        repository_root,
        commit=ATTACH_AMENDMENT_COMMIT,
        expected_tree=ATTACH_AMENDMENT_TREE,
        require_current_source=False,
    )
    historical_files = (
        (V2_PROTOCOL_COMMIT, V2_PROTOCOL_PATH, V2_PROTOCOL_SHA256),
        (PRE_RESPONSE_FREEZE_COMMIT, PRE_RESPONSE_PREDICTION_PATH, PRE_RESPONSE_PREDICTION_SHA256),
        (PRE_RESPONSE_FREEZE_COMMIT, PRE_RESPONSE_BINS_PATH, PRE_RESPONSE_BINS_SHA256),
        (PRE_RESPONSE_FREEZE_COMMIT, PRE_RESPONSE_RECEIPT_PATH, PRE_RESPONSE_RECEIPT_SHA256),
        (
            PRE_RESPONSE_FREEZE_COMMIT,
            PRE_RESPONSE_PACKAGE_MANIFEST_PATH,
            PRE_RESPONSE_PACKAGE_MANIFEST_SHA256,
        ),
        (
            PRE_RESPONSE_FREEZE_COMMIT,
            PRE_RESPONSE_RANKINGS_PACKAGE_PATH,
            PRE_RESPONSE_RANKINGS_PACKAGE_SHA256,
        ),
        (
            ATTACH_FAILURE_EVIDENCE_COMMIT,
            ATTACH_FAILURE_RECEIPT_PATH,
            ATTACH_FAILURE_RECEIPT_SHA256,
        ),
        (
            ATTACH_FAILURE_EVIDENCE_COMMIT,
            ATTACH_FAILURE_OUTPUT_PATH,
            ATTACH_FAILURE_OUTPUT_SHA256,
        ),
        (ATTACH_AMENDMENT_COMMIT, ATTACH_AMENDMENT_PATH, ATTACH_AMENDMENT_SHA256),
    )
    for historical_commit, relative, digest in historical_files:
        _validate_historical_file(
            repository_root,
            commit=historical_commit,
            relative_path=relative,
            expected_sha256=digest,
        )


def _validate_supersession_v2(value: object, *, repository_root: Path) -> None:
    supersession = _mapping(value, "supersession")
    expected = {
        "base_protocol": {
            "path": BASE_PROTOCOL_PATH,
            "sha256": BASE_PROTOCOL_SHA256,
            "semantic_digest": BASE_PROTOCOL_DIGEST,
            "commit": BASE_PROTOCOL_COMMIT,
        },
        "failure_evidence": {
            "commit": FAILURE_EVIDENCE_COMMIT,
            "tree": FAILURE_EVIDENCE_TREE,
            "amendment_path": FAILURE_AMENDMENT_PATH,
            "amendment_sha256": FAILURE_AMENDMENT_SHA256,
            "amendment_digest": FAILURE_AMENDMENT_DIGEST,
            "receipt_path": FAILURE_RECEIPT_PATH,
            "receipt_sha256": FAILURE_RECEIPT_SHA256,
            "receipt_digest": FAILURE_RECEIPT_DIGEST,
        },
        "attempt_1": {
            "status": "failed_closed",
            "candidate_propagation_function_invocations": 377,
            "frozen_ranking_helper_invocations": 564,
            "candidate_results_printed": False,
            "candidate_results_inspected": False,
            "candidate_results_persisted": False,
            "process_memory_inspected": False,
            "odd_iq_accessed": False,
            "odd_responses_accessed": False,
            "shared_rate_diagnostic_executed": False,
            "pre_response_rankings_persisted": False,
            "pre_response_receipt_persisted": False,
            "combined_command_output_path": FAILURE_COMBINED_OUTPUT_PATH,
            "combined_command_output_sha256": FAILURE_COMBINED_OUTPUT_SHA256,
            "stdout_stderr_separation_preserved": False,
            "separate_stdout_byte_size": None,
            "separate_stderr_byte_size": None,
            "prediction_ledger_path": ATTEMPT_1_PREDICTION_PATH,
            "prediction_ledger_sha256": ATTEMPT_1_PREDICTION_SHA256,
            "prediction_ledger_digest": ATTEMPT_1_PREDICTION_DIGEST,
            "association_bins_path": ATTEMPT_1_BINS_PATH,
            "association_bins_sha256": ATTEMPT_1_BINS_SHA256,
            "association_bins_digest": ATTEMPT_1_BINS_DIGEST,
        },
        "response_free_correction": {
            "integer_utc_median_rule": (
                "sort integer nanoseconds; odd selects the middle value; even averages "
                "the two middle integers with round-to-nearest/ties-to-even using "
                "quotient-and-remainder arithmetic"
            ),
            "attempt_1_bin_center_count": 307,
            "corrected_bin_center_change_count": 307,
            "corrected_minus_attempt_1_min_ns": -197,
            "corrected_minus_attempt_1_max_ns": 173,
            "corrected_maximum_absolute_change_ns": 197,
            "final_bin_change_ns": -22,
            "membership_cfo_medians_splits_and_support_unchanged": True,
            "rolling_controls_preflighted_before_tle_reader_and_candidate_work": True,
            "candidate_outcomes_used": False,
            "odd_iq_or_responses_used": False,
            "prediction_model_changed": False,
            "association_model_or_controls_changed": False,
            "thresholds_or_claim_gates_changed": False,
            "expected_prediction_ledger_sha256": ATTEMPT_1_PREDICTION_SHA256,
            "expected_prediction_ledger_digest": ATTEMPT_1_PREDICTION_DIGEST,
            "expected_corrected_bins_sha256": CORRECTED_BINS_SHA256,
            "expected_corrected_bins_digest": CORRECTED_BINS_DIGEST,
        },
        "execution": {
            "v1_retired": True,
            "v2_required": True,
            "future_failure_status_schema": (
                "org.leo.research.final-holdout-pre-response-failure-status/v1"
            ),
            "future_failure_status_basename": "pre-response-failure-status.json",
        },
    }
    if supersession != expected:
        raise ValueError("final holdout v2 supersession authority drifted")
    for path, digest in (
        (BASE_PROTOCOL_PATH, BASE_PROTOCOL_SHA256),
        (FAILURE_AMENDMENT_PATH, FAILURE_AMENDMENT_SHA256),
        (FAILURE_RECEIPT_PATH, FAILURE_RECEIPT_SHA256),
        (FAILURE_COMBINED_OUTPUT_PATH, FAILURE_COMBINED_OUTPUT_SHA256),
        (ATTEMPT_1_PREDICTION_PATH, ATTEMPT_1_PREDICTION_SHA256),
        (ATTEMPT_1_BINS_PATH, ATTEMPT_1_BINS_SHA256),
    ):
        if _sha256_tag(repository_root / path) != digest:
            raise ValueError(f"final holdout v2 supersession bytes drifted: {path}")
    _validate_historical_file(
        repository_root,
        commit=BASE_PROTOCOL_COMMIT,
        relative_path=BASE_PROTOCOL_PATH,
        expected_sha256=BASE_PROTOCOL_SHA256,
    )
    _validate_git_implementation_commit(
        repository_root,
        commit=FAILURE_EVIDENCE_COMMIT,
        expected_tree=FAILURE_EVIDENCE_TREE,
        require_current_source=False,
    )
    _validate_historical_file(
        repository_root,
        commit=FAILURE_EVIDENCE_COMMIT,
        relative_path=FAILURE_AMENDMENT_PATH,
        expected_sha256=FAILURE_AMENDMENT_SHA256,
    )
    _validate_historical_file(
        repository_root,
        commit=FAILURE_EVIDENCE_COMMIT,
        relative_path=FAILURE_RECEIPT_PATH,
        expected_sha256=FAILURE_RECEIPT_SHA256,
    )
    _validate_historical_file(
        repository_root,
        commit=FAILURE_EVIDENCE_COMMIT,
        relative_path=FAILURE_COMBINED_OUTPUT_PATH,
        expected_sha256=FAILURE_COMBINED_OUTPUT_SHA256,
    )
    _validate_historical_file(
        repository_root,
        commit=FAILURE_EVIDENCE_COMMIT,
        relative_path=ATTEMPT_1_PREDICTION_PATH,
        expected_sha256=ATTEMPT_1_PREDICTION_SHA256,
    )
    _validate_historical_file(
        repository_root,
        commit=FAILURE_EVIDENCE_COMMIT,
        relative_path=ATTEMPT_1_BINS_PATH,
        expected_sha256=ATTEMPT_1_BINS_SHA256,
    )


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


def _validate_chunks(
    value: object,
    *,
    expected: tuple[tuple[object, ...], ...] = _EXPECTED_CHUNKS_V1_V2,
) -> None:
    if not isinstance(value, list) or len(value) != len(expected):
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
    if observed != expected:
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
    require_current_source: bool,
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
    if not require_current_source:
        return
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


def _sha256_tag_at_commit(
    repository_root: Path,
    *,
    commit: str,
    relative_path: str,
) -> str:
    try:
        payload = subprocess.run(
            ["git", "show", f"{commit}:{relative_path}"],
            cwd=repository_root,
            check=True,
            capture_output=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError) as error:
        raise ValueError(f"historical implementation is unavailable: {relative_path}") from error
    return "sha256:" + hashlib.sha256(payload).hexdigest()


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
