from __future__ import annotations

from dataclasses import replace

import pytest

from leo.catalog import CatalogProductRecord
from leo.pipeline import ProductRequirement, ScopeIdentityV1
from leo.processing.adapters import CatalogArtifactProductReader

DIGEST = "sha256:" + "a" * 64


class _Catalog:
    def __init__(self, rows):
        self.rows = rows

    def authorized_job_input_products(self, job_id: int):
        assert job_id == 7
        return self.rows


class _Artifacts:
    def read_json(self, logical_uri: str, digest: str):
        assert digest == DIGEST
        return {"uri": logical_uri}


def _record(index: int) -> CatalogProductRecord:
    scope = ScopeIdentityV1.receiver_path(
        session_id="T1", stream_id=f"stream-{index // 2}", receiver_id=index % 2
    )
    return CatalogProductRecord(
        product_id=index + 1,
        run_id="run",
        stage_key="path-report",
        scope_key=scope.canonical_digest,
        kind="path.report",
        schema_version=1,
        role="scientific",
        status="complete",
        media_type="application/json",
        logical_uri=f"bulk://analysis/path-{index}.json",
        digest=DIGEST,
        byte_size=10,
        available=True,
        coverage=1.0,
        summary={},
        scope_id=index + 1,
        scope=scope,
    )


@pytest.mark.parametrize("count", (1, 2, 3, 4))
def test_exact_node_fanin_supports_all_standard_topology_widths(count: int) -> None:
    nodes = tuple(f"path-{index}" for index in range(count))
    rows = tuple((node, _record(index)) for index, node in enumerate(nodes))
    reader = CatalogArtifactProductReader(
        _Catalog(rows),  # type: ignore[arg-type]
        _Artifacts(),  # type: ignore[arg-type]
        run_id="run",
        scope_key="unused",
        job_id=7,
    )

    products = reader.read_json_many(
        ProductRequirement(kind="path.report", producer_stage_key="path-report"),
        producer_node_ids=nodes,
    )

    assert tuple(item.producer_node_id for item in products) == nodes
    assert reader.consumed_product_ids == tuple(range(1, count + 1))


def test_exact_node_fanin_rejects_reordering_omission_extra_and_ambiguity() -> None:
    nodes = ("path-0", "path-1")
    rows = ((nodes[0], _record(0)), (nodes[1], _record(1)))
    requirement = ProductRequirement(kind="path.report")

    def reader_for(candidate_rows=rows):
        return CatalogArtifactProductReader(
            _Catalog(candidate_rows),  # type: ignore[arg-type]
            _Artifacts(),  # type: ignore[arg-type]
            run_id="run",
            scope_key="unused",
            job_id=7,
        )

    for requested in (("path-1", "path-0"), ("path-0",), ("path-0", "path-1", "path-2")):
        with pytest.raises(ValueError):
            reader_for().read_json_many(requirement, producer_node_ids=requested)

    duplicate = replace(_record(0), product_id=99)
    with pytest.raises(ValueError, match="ambiguous"):
        reader_for(rows + (("path-0", duplicate),)).read_json_many(
            requirement, producer_node_ids=nodes
        )
