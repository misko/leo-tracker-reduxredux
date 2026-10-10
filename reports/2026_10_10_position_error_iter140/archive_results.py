"""Full193 terminal raw archive, independent of accuracy evaluation."""

import gzip
import importlib.util
import json
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location(
    "safe137archive_for140", HERE.parent / "2026_10_10_position_error_iter137/archive_inputs.py"
)
SAFE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SAFE)
TERMINAL = {"complete", "failed", "attempt-failed", "model-integrity-failed"}


def prepare_files(here, root):
    protocol = here / "protocol.json"
    plan = json.loads(protocol.read_text())
    if len(plan["members"]) != 193 or len({m["label"] for m in plan["members"]}) != 193:
        raise ValueError("Full193 membership required")
    protocol_sha = SAFE.digest(protocol.read_bytes())
    for relative, expected in {**plan["sources"], **plan["inputs"]}.items():
        if SAFE.digest((root / relative).read_bytes()) != expected:
            raise ValueError("Frozen input/source mismatch")
    paths = []
    for binding in plan["members"]:
        label = binding["label"]
        if Path(label).name != label:
            raise ValueError("Unsafe member label")
        result = here / "results" / (label + ".json")
        claim = result.with_suffix(".claim.json")
        for artifact in (result, claim):
            value = json.loads(artifact.read_text())
            if value["label"] != label or value["protocol_sha256"] != protocol_sha:
                raise ValueError("Foreign result/claim")
            paths.append(artifact)
        if json.loads(result.read_text())["status"] not in TERMINAL:
            raise ValueError("Nonterminal result")
    if set((here / "results").glob("*.json")) != set(paths):
        raise ValueError("Unbound raw result files")
    return protocol_sha, sorted(paths)


def create(here=HERE, root=ROOT):
    protocol_sha, paths = prepare_files(here, root)
    manifest = {
        str(p.relative_to(here)): dict(bytes=p.stat().st_size, sha256=SAFE.digest(p.read_bytes()))
        for p in paths
    }
    target = here / "results.tar.gz"
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
    value = dict(
        protocol_sha256=protocol_sha,
        files=manifest,
        archive_bytes=target.stat().st_size,
        archive_sha256=SAFE.digest(target.read_bytes()),
    )
    with tempfile.TemporaryDirectory() as directory:
        SAFE.restore(target, value, directory)
    with (here / "RESULT_ARCHIVE.json").open("x") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")
    return value


if __name__ == "__main__":
    result = create()
    print(json.dumps({k: v for k, v in result.items() if k != "files"}))
