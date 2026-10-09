"""Deterministic terminal-only archive; preserves every original receipt."""

import gzip
import hashlib
import io
import json
import tarfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHUNK_THRESHOLD = 90 * 1024 * 1024
CHUNK_SIZE = 40 * 1024 * 1024


def immutable(path, data):
    if path.exists():
        assert path.read_bytes() == data, f"Refusing replacement: {path}"
    else:
        with path.open("xb") as stream:
            stream.write(data)


def archive(here=HERE):
    here = Path(here)
    protocol_bytes = (here / "protocol.json").read_bytes()
    plan = json.loads(protocol_bytes)
    digest = hashlib.sha256(protocol_bytes).hexdigest()
    members = {b["member"]["inventory_label"]: b["member"] for b in plan["members"]}
    assert set(members) == set(plan["labels"]) and len(members) == 148
    statuses, attempts = Counter(), Counter()
    for label, member in members.items():
        row = json.loads((here / "results" / f"{label}.json").read_text())
        assert row["protocol_sha256"] == digest and row["member"] == member
        assert row["status"] in ("complete", "failed")
        statuses[row["status"]] += 1
        if row["status"] == "complete":
            for width in ("125", "100"):
                for arm in ("fitted-c", "zero-c"):
                    attempt = json.loads(
                        (here / "attempts" / label / f"sigma{width}-{arm}.json").read_text()
                    )
                    assert attempt == row["raw"][width][arm]
    payload = {}
    for folder in ("results", "attempts", "controller-claims"):
        for path in sorted((here / folder).rglob("*.json")):
            assert not path.is_symlink()
            data = path.read_bytes()
            row = json.loads(data)
            assert row["protocol_sha256"] == digest, path
            if folder == "attempts":
                label = path.parent.name
                assert row["member"] == members[label]
                assert row["status"] in ("complete", "failed")
                attempts[row["status"]] += 1
                if row["status"] == "complete":
                    attempts["qualified" if row["fit"]["converged"] else "unqualified"] += 1
            elif folder == "results":
                assert path.stem in members
            else:
                label = path.name.removesuffix(".exit.json").removesuffix(".json")
                assert label in members
                if not path.name.endswith(".exit.json"):
                    assert row["label"] == label
                    assert path.with_suffix(".exit.json").exists(), "Controller still active"
            payload[str(path.relative_to(here))] = data
    payload = dict(sorted(payload.items()))
    output = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=output, mode="wb", filename="", mtime=0) as compressed,
        tarfile.open(fileobj=compressed, mode="w", format=tarfile.PAX_FORMAT) as tar,
    ):
        for name, data in payload.items():
            info = tarfile.TarInfo(name)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            tar.addfile(info, io.BytesIO(data))
    compressed_bytes = output.getvalue()
    with tarfile.open(fileobj=io.BytesIO(compressed_bytes), mode="r:gz") as tar:
        assert tar.getnames() == list(payload)
        for member in tar.getmembers():
            assert member.isfile() and tar.extractfile(member).read() == payload[member.name]
    assert all((here / name).read_bytes() == data for name, data in payload.items())
    immutable(here / "results-receipts.tar.gz", compressed_bytes)
    manifest = dict(
        protocol_sha256=digest,
        archive_sha256=hashlib.sha256(compressed_bytes).hexdigest(),
        archive_bytes=len(compressed_bytes),
        terminal_statuses=dict(statuses),
        attempt_statuses=dict(attempts),
        raw_local_preserved=True,
        readback_verified=True,
        files={
            name: dict(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            for name, data in payload.items()
        },
    )
    if len(compressed_bytes) > CHUNK_THRESHOLD:
        manifest["parts"] = []
        for index, start in enumerate(range(0, len(compressed_bytes), CHUNK_SIZE)):
            data = compressed_bytes[start : start + CHUNK_SIZE]
            name = f"results-receipts.tar.gz.part{index:03d}"
            immutable(here / name, data)
            manifest["parts"].append(
                dict(name=name, bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            )
    immutable(
        here / "results-receipts-manifest.json", (json.dumps(manifest, indent=2) + "\n").encode()
    )
    return manifest


if __name__ == "__main__":
    print(json.dumps(archive(), indent=2))
