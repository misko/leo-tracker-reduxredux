"""Byte-pinned decoder coverage for historical CFO product majors.

These fixtures are copied verbatim from durable, sealed production products.
They protect read compatibility while obsolete producer implementations are
retired from the runtime package.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from leo.analysis.standard.codecs import decode_standard_product
from leo.analysis.standard.products import (
    CFO_LIFT_REPLAY_V1_PRODUCT,
    CFO_LIFT_REPLAY_V3_PRODUCT,
    DEALIASED_TRAJECTORY_BANK_V2_PRODUCT,
    FINAL_TRAJECTORY_BANK_V1_PRODUCT,
    FINAL_TRAJECTORY_BANK_V2_PRODUCT,
    GLRT64_FINAL_TRAJECTORY_TABLE_V1_PRODUCT,
    GLRT64_FINAL_TRAJECTORY_TABLE_V2_PRODUCT,
)
from leo.pipeline import ProductSpec

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "historical_cfo_products"


@pytest.mark.parametrize(
    ("filename", "sha256", "product"),
    (
        (
            "standard.cfo-lift-replay.v1.json",
            "5f4f3876e03962ccef6b7842ef5260f18c33646acaf1aaa662747913f3009a67",
            CFO_LIFT_REPLAY_V1_PRODUCT,
        ),
        (
            "standard.cfo-lift-replay.v3.json",
            "0b0bef2b91344292c5ab1c1f70929e9670d37c996b9f1ea7f2fa6a7d1f2cddb3",
            CFO_LIFT_REPLAY_V3_PRODUCT,
        ),
        (
            "standard.dealiased-trajectory-bank.v2.json",
            "7f70309e5fe137cf87de86ebac0d93272d2bd66ad0eceaef9f34dfeba889d7b7",
            DEALIASED_TRAJECTORY_BANK_V2_PRODUCT,
        ),
        (
            "standard.final-trajectory-bank.v1.json",
            "5369da0dfc5ba63895646d8ec67152d523b407f50817fdfa2f3c8072003a9606",
            FINAL_TRAJECTORY_BANK_V1_PRODUCT,
        ),
        (
            "standard.final-trajectory-bank.v2.json",
            "4e330a8b446bc11c8c96f052c0104d746561cc620e09aa4c6987e94d119d67dd",
            FINAL_TRAJECTORY_BANK_V2_PRODUCT,
        ),
        (
            "standard.glrt64-final-trajectory-table.v1.json",
            "813fc8c38ed0cbd71de3d353a4975ab5e80b1f4b40d43e2b56ee2cc840029844",
            GLRT64_FINAL_TRAJECTORY_TABLE_V1_PRODUCT,
        ),
        (
            "standard.glrt64-final-trajectory-table.v2.json",
            "b3393c36d5acaedb9de986aa82e869438b6a88d4a37c8a397fe8186697ff97ba",
            GLRT64_FINAL_TRAJECTORY_TABLE_V2_PRODUCT,
        ),
    ),
)
def test_historical_cfo_product_decoders_remain_byte_compatible(
    filename: str,
    sha256: str,
    product: ProductSpec,
) -> None:
    payload = (_FIXTURES / filename).read_bytes()
    assert hashlib.sha256(payload).hexdigest() == sha256
    document = json.loads(payload)
    assert decode_standard_product(product, document) == document
