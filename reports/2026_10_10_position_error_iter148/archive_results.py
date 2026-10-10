"""Deterministic complete-branch archive; no model or evaluation ports."""

import argparse
import gzip
import importlib.util
import json
import tarfile
import tempfile
from pathlib import Path

from leo.contracts.digests import canonical_digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location(
    "safe137_for148", HERE.parent / "2026_10_10_position_error_iter137/archive_inputs.py"
)
SAFE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SAFE)


def prepare(here, root):
    plan = json.loads((here / "protocol.json").read_text())
    digest = canonical_digest(plan)
    for group in ("source_sha256", "input_sha256", "evaluation_source_sha256"):
        for name, expected in plan[group].items():
            if SAFE.digest((root / name).read_bytes()) != expected:
                raise ValueError("Frozen source/input changed")
    if set(plan["branches"]) != {"native", "zero"} or any(
        len(v) != 3 for v in plan["branches"].values()
    ):
        raise ValueError("Exact three regions per branch required")
    paths = []
    for branch in ("native", "zero"):
        folder = here / "results" / branch
        terminal = json.loads((folder / "result.json").read_text())
        if terminal.get("branch") != branch or terminal.get("status") not in (
            "complete",
            "failed",
            "budget-exhausted",
        ):
            raise ValueError("Both branches must have bound terminal receipts")
        for path in folder.rglob("*.json"):
            value = json.loads(path.read_text())
            if value.get("protocol_sha256") != digest:
                raise ValueError("Foreign raw receipt")
            if path.name.endswith(".claim.json"):
                completed = path.with_name(path.name.replace(".claim.json", ".json"))
                if not completed.exists():
                    raise ValueError("Unresolved stage claim")
            paths.append(path)
    summary = here / "SUMMARY.json"
    value = json.loads(summary.read_text())
    if value.get("protocol_sha256") != digest or not value.get("both_terminal"):
        raise ValueError("Unbound summary")
    return digest, sorted(paths + [summary])


def create(here=HERE, root=ROOT):
    digest, paths = prepare(here, root)
    target = here / "results-summary.tar.gz"
    manifest = dict(
        protocol_sha256=digest,
        files={
            str(p.relative_to(here)): dict(
                bytes=p.stat().st_size, sha256=SAFE.digest(p.read_bytes())
            )
            for p in paths
        },
    )
    with (
        target.open("xb") as raw,
        gzip.GzipFile(filename="", fileobj=raw, mode="wb", mtime=0) as gz,
        tarfile.open(fileobj=gz, mode="w|") as archive,
    ):
        for path in paths:
            info = tarfile.TarInfo(str(path.relative_to(here)))
            info.size, info.mode = path.stat().st_size, 0o644
            with path.open("rb") as stream:
                archive.addfile(info, stream)
    manifest.update(
        archive_sha256=SAFE.digest(target.read_bytes()), archive_bytes=target.stat().st_size
    )
    with tempfile.TemporaryDirectory() as directory:
        SAFE.restore(target, manifest, directory)
    with (here / "RESULT_ARCHIVE.json").open("x") as stream:
        json.dump(manifest, stream, indent=2, allow_nan=False)
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--restore-to", type=Path)
    args = parser.parse_args()
    if args.restore_to is None:
        result = create()
        print(result["archive_bytes"], result["archive_sha256"])
    else:
        SAFE.restore(
            HERE / "results-summary.tar.gz",
            json.loads((HERE / "RESULT_ARCHIVE.json").read_text()),
            args.restore_to,
        )
