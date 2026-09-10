"""Publish an explicit, non-secret evidence whitelist and existing local PNGs."""

import argparse
import gzip
import hashlib
import json
import urllib.request
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    if not str(source).startswith("/srv/bulk/leo/scanner-r21-only-"):
        parser.error("expected the scoped local .21 verification directory")
    evidence = Path(__file__).resolve().parent
    figures = evidence.parents[1] / "figures" / evidence.name
    figures.mkdir(parents=True, exist_ok=True)
    saved = []

    def save(destination, payload):
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as stream:
            stream.write(payload)
        saved.append(
            dict(
                path=str(destination.relative_to(evidence.parents[1])),
                sha256=hashlib.sha256(payload).hexdigest(),
                bytes=len(payload),
            )
        )

    identity = json.loads((source / "identity.json").read_bytes())
    save(
        evidence / "identity.json",
        json.dumps(
            {key: identity[key] for key in ("network", "boot_id", "attributes")}, indent=2
        ).encode(),
    )
    for name in (
        "cutover-result.json",
        "startup-fix-cutover-result.json",
        "single-host-credential-result.json",
        "sealed-release-receipt.json",
        "recover_1620.py",
    ):
        payload = (source / name).read_bytes()
        if name.endswith(".py"):
            save(evidence / (name + ".gz"), gzip.compress(payload, mtime=0))
        else:
            save(evidence / name, payload)
    for kind in ("fixed", "adaptive"):
        for name in ("verification.json", "manifest.json.gz", "glrt-publication.json.gz"):
            save(evidence / kind / name, (source / f"verified-{kind}" / name).read_bytes())
        save(
            evidence / kind / "ui-verification.json",
            (source / f"ui-{kind}" / "ui-verification.json").read_bytes(),
        )
        publication = json.loads(
            (source / f"figures-{kind}" / "publication-verification.json").read_bytes()
        )
        save(
            evidence / kind / "publication-verification.json",
            json.dumps(publication, indent=2).encode(),
        )
        for artifact in publication["artifacts"]:
            assert artifact["http_status"] == 200 and artifact["content_type"] == "image/png"
            payload = (source / f"figures-{kind}" / (artifact["name"] + ".png")).read_bytes()
            assert hashlib.sha256(payload).hexdigest() == artifact["sha256"]
            save(figures / f"{kind}-{artifact['name']}.png", payload)
    tracking = source / "figures-tracking"
    save(
        evidence / "fixed" / "tracking-verification.json",
        (tracking / "publication-verification.json").read_bytes(),
    )
    save(figures / "fixed-trajectory-tle.png", (tracking / "trajectory-tle.png").read_bytes())
    save(
        evidence / "original-missing-ui.json",
        (source / "ui-original-missing" / "ui-verification.json").read_bytes(),
    )
    snapshots = {}
    for name, route in (
        ("capture_control", "/api/v1/capture-control"),
        ("acquisition_queue", "/api/v1/acquisition-queue?limit=10"),
    ):
        with urllib.request.urlopen("http://127.0.0.1:8090" + route, timeout=20) as response:
            snapshots[name] = json.load(response)
    assert snapshots["capture_control"]["desired_state"] == "running"
    ordinary = [
        item for item in snapshots["acquisition_queue"]["items"] if item["operation_id"] == 9923
    ]
    assert len(ordinary) == 1 and ordinary[0]["attempt_count"] == 0
    assert ordinary[0]["state"] == "pending"
    save(evidence / "final-public-state.json", json.dumps(snapshots, indent=2).encode())
    save(evidence / "index.json", json.dumps(saved, indent=2).encode())
    print(json.dumps(dict(files=len(saved), figures=str(figures))))


if __name__ == "__main__":
    main()
