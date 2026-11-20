"""Resolve a frozen recording's installed producer from its acquisition receipts."""

import json
from hashlib import sha256
from pathlib import Path

from .full_v5_check import BULK, PRODUCERS, Producer

RELEASE_ROOTS = {
    "fast-1f3a91c6a882b6e7eac8827fbb95f215": PRODUCERS["DS26-0036"].root,
    "fast-33b3892e0162eac7fd2232898aa9d1ce": PRODUCERS["DS29-0082"].root,
    "fast-a9ce664313cc56759cdffefe4750f833": Path(
        "/opt/leo-native-glrt-runtime/a1b999aad5bdc924fd90d35e055878bc23bd4c06/src"
    ),
}


class UnsupportedCaptureRelease(ValueError):
    """The archived run cannot be reproduced by an installed producer on this host."""


def inventory_digest(segments, window_count):
    from leo.contracts.digests import canonical_digest

    return canonical_digest(
        dict(
            schema_version=1,
            kind="fast-scan-source",
            recording_name=Path(segments[0]["path"]).parent.name,
            segments=segments,
            window_count=window_count,
        )
    )


def producer(case, capture):
    from leo.contracts.digests import canonical_digest

    digest = capture["input_manifest_sha256"]
    if case["session_id"] != "fast-" + digest[7:39] or capture["edge"] not in ("upper", "lower"):
        raise ValueError("capture receipt differs from the frozen session or pilot edge")
    for release, root in RELEASE_ROOTS.items():
        run = canonical_digest([case["session_id"], digest, release])
        if case["run_id"] == "fast-" + run[7:39]:
            return Producer(root, digest)
    raise UnsupportedCaptureRelease(f"no verified installed producer for {case['id']}")


def read_capture(case):
    from tools.pipeline_eval.variants.iq_stream import _read_prefix

    inventory, edges = [], set()
    for index, locator in enumerate(case["recording"]["segments"]):
        path = BULK / locator["path"]
        data = _read_prefix(path, 65537)
        if len(data) > 65536 or sha256(data).hexdigest() != locator["sha256"]:
            raise ValueError(f"capture manifest failed authentication: {path}")
        manifest = json.loads(data)
        if (
            manifest["session_id"] != path.parent.name
            or manifest["status"] != "complete"
            or manifest["sample_rate_hz"] != 10_000_000
            or manifest["window_ms"] != 20
            or manifest["receiver_ids"] != [0, 1]
            or manifest["sample_format"] != "ci16_le"
            or manifest["sample_layout"] != "sample_receiver_iq"
        ):
            raise ValueError(f"unsupported recording geometry or incomplete manifest: {path}")
        edges.update(target["edge"] for target in manifest["configuration"]["targets"])
        inventory.append(
            dict(
                scope=f"segment-{index:08d}",
                path=str(path.parent),
                manifest_digest="sha256:" + locator["sha256"],
                windows=manifest["window_count"],
            )
        )
    count = case["recording"]["window_count"]
    if not inventory or len(edges) != 1 or sum(s["windows"] for s in inventory) != count:
        raise ValueError("capture inventory needs one pilot edge and all scheduled windows")
    capture = dict(edge=edges.pop(), input_manifest_sha256=inventory_digest(inventory, count))
    producer(case, capture)
    return capture
