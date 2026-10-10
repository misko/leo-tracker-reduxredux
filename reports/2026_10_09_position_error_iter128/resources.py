"""Public manifest metadata only: never creates an IQ reader."""

import json
from pathlib import Path

from run import digest, write_new

from leo.storage.adaptive_hop import AdaptiveHopIqStore

HERE = Path(__file__).resolve().parent


def main():
    inventory = json.loads((HERE / "inventory.json").read_text())
    store = AdaptiveHopIqStore(Path("/srv/bulk/leo"), read_only=True)
    rows = []
    for member in inventory["members"]:
        capture = store.inspect(member["session_id"])
        if capture.manifest_sha256 != member["input_manifest_sha256"]:
            raise ValueError("manifest mismatch")
        rows.append(
            {
                "label": member["label"],
                "manifest_sha256": capture.manifest_sha256,
                "chunks": len(capture.manifest.chunks),
                "maximum_compressed_bytes": max(
                    c.compressed_bytes for c in capture.manifest.chunks
                ),
                "maximum_uncompressed_bytes": max(
                    c.uncompressed_bytes for c in capture.manifest.chunks
                ),
            }
        )
    write_new(
        HERE / "resources.json",
        {"inventory_sha256": digest(HERE / "inventory.json"), "iq_reads": 0, "members": rows},
    )


if __name__ == "__main__":
    main()
