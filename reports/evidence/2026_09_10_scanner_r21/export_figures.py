"""Export existing local science PNGs; verify the deployed API serves identical bytes."""

import argparse
import hashlib
import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore
from leo.storage.persistent_hop_analysis_v2 import PersistentHopAnalysisStoreV2
from leo.storage.persistent_hop_tracking import PersistentHopTrackingStore


def fetch(url):
    with urllib.request.urlopen(url, timeout=30) as response:
        return response.read(), response.status, response.headers.get_content_type()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kind", choices=("fixed", "adaptive", "tracking"))
    parser.add_argument("session")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if not args.output.is_absolute() or str(args.output).startswith("/mnt/qnap01"):
        parser.error("output must be an absolute local path outside QNAP")
    root = Path("/srv/bulk/leo")
    base = "http://127.0.0.1:8090"
    if args.kind == "adaptive":
        store = AdaptiveHopAnalysisPresentationStore(root)
        status = store.status(args.session, probe_stride_ms=120)
        assert status is not None and status.state == "figures_ready" and status.overview
        artifacts = status.overview.artifacts
        details = status.model_dump(mode="json")
    elif args.kind == "tracking":
        store = PersistentHopTrackingStore.open_read_only(root)
        details = json.loads(
            fetch(f"{base}/api/v4/scanner/persistent-sessions/{args.session}/tracking")[0]
        )
        assert details["status"]["state"] == "complete"
        artifacts = ("trajectory-tle",)
    else:
        store = PersistentHopAnalysisStoreV2.open_read_only(root)
        assert store.is_complete(args.session)
        artifacts = ("coverage", "glrt64-response", "cfo-trajectories")
        details = json.loads(fetch(f"{base}/api/v3/scanner/persistent-sessions/{args.session}")[0])
    args.output.mkdir(parents=True, exist_ok=False)
    results = []
    for artifact in artifacts:
        if args.kind == "adaptive":
            name = artifact.name
            payload = store.artifact(
                args.session,
                name,
                binding_sha256=status.binding_sha256,
                artifact_sha256=artifact.sha256,
                probe_stride_ms=120,
            )
            query = urlencode(
                dict(
                    probe_stride_ms=120,
                    binding_sha256=status.binding_sha256,
                    artifact_sha256=artifact.sha256,
                )
            )
            url = (
                f"{base}/api/v1/scanner/adaptive-sessions/{args.session}"
                f"/analysis/{name}.png?{query}"
            )
        elif args.kind == "tracking":
            name = artifact
            payload = store.artifact(args.session)
            url = f"{base}/api/v4/scanner/persistent-sessions/{args.session}/{name}.png"
        else:
            name = artifact
            payload = store.artifact(args.session, name)
            url = f"{base}/api/v3/scanner/persistent-sessions/{args.session}/{name}.png"
        assert payload and payload.startswith(b"\x89PNG\r\n\x1a\n")
        served, code, content_type = fetch(url)
        assert served == payload and code == 200 and content_type == "image/png"
        (args.output / f"{name}.png").write_bytes(payload)
        results.append(
            dict(
                name=name,
                bytes=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
                http_status=code,
                content_type=content_type,
                url=url,
            )
        )
    result = dict(
        verified_at=datetime.now(UTC).isoformat(),
        session_id=args.session,
        kind=args.kind,
        artifacts=results,
        public_analysis=details,
    )
    with (args.output / "publication-verification.json").open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps({key: value for key, value in result.items() if key != "public_analysis"}))


if __name__ == "__main__":
    main()
