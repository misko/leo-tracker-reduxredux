"""Stage an explicit immutable release; inspect services but never switch them.

The input manifest enumerates every file, including any inherited runtime files.
No recursive research checkout overlay, dependency discovery or service mutation
is performed. A failed stage is retained with its failure receipt.
"""

import argparse
import hashlib
import json
import os
import shlex
import stat
import subprocess
from pathlib import Path, PurePosixPath

SCHEMA = "fast-shared-explicit-release-v1"
SERVICES = ("leo-fast-scan-analysis.service", "leo-api.service")


def digest(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()


def binding(path):
    path = Path(path)
    return dict(path=str(path), sha256=digest(path.read_bytes()))


def prepare_patch(specification, output):
    """Materialize reviewed narrow edits from pinned deployed bytes, never in place.

    The resulting file becomes an ordinary explicit manifest source. There is no
    fuzzy application: every old span must occur exactly once in the source at
    the moment it is replaced. The declared result digest is mandatory.
    """
    output = Path(output)
    source = Path(specification["source"])
    if output.exists() or not output.is_absolute() or source.resolve() == output.resolve():
        raise ValueError("Fresh absolute patch output outside source required")
    original = source.read_bytes()
    if digest(original) != specification["source_sha256"]:
        raise ValueError("Deployed patch base changed")
    edits = specification.get("replacements")
    if not isinstance(edits, list) or not 1 <= len(edits) <= 20:
        raise ValueError("Bounded explicit patch spans required")
    text = original.decode("utf-8")
    for edit in edits:
        before, after = edit["old"], edit["new"]
        if not isinstance(before, str) or not before or not isinstance(after, str):
            raise ValueError("Nonempty exact old span required")
        if text.count(before) != 1:
            raise ValueError("Patch span absent or ambiguous; no fuzzy application")
        text = text.replace(before, after, 1)
    result = text.encode("utf-8")
    if digest(result) != specification["result_sha256"]:
        raise ValueError("Reviewed patched result digest differs")
    if source.read_bytes() != original:
        raise ValueError("Deployed patch base changed during preparation")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream:
        stream.write(result)
        stream.flush()
        os.fsync(stream.fileno())
    return dict(source=binding(source), patched=binding(output), replacements=len(edits))


def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write((json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())


def validate(document, destination):
    destination = Path(destination)
    if document.get("schema") != SCHEMA or not document.get("model_id"):
        raise ValueError("Explicit versioned model/release manifest required")
    if not destination.is_absolute() or destination.exists() or destination.is_symlink():
        raise ValueError("New absolute release destination required")
    files, seen = document.get("files"), set()
    if not isinstance(files, list) or not 1 <= len(files) <= 2000:
        raise ValueError("Explicit bounded file inventory required")
    for row in files:
        name = row["target"]
        relative = PurePosixPath(name)
        if (
            not isinstance(name, str)
            or relative.is_absolute()
            or ".." in relative.parts
            or str(relative) != name
            or name in seen
            or name in {"stage.json", "failure.json", "input-manifest.json"}
            or not relative.parts
            or relative.parts[0] not in {"worker", "api", "bin", "web"}
        ):
            raise ValueError("Unique canonical relative release file required")
        seen.add(name)
        source = Path(row["source"])
        if (
            not source.is_absolute()
            or not source.is_file()
            or source.resolve().is_relative_to(destination.resolve())
        ):
            raise ValueError("Existing source outside new release required")
        if row.get("mode") not in (0o444, 0o555):
            raise ValueError("Immutable read-only or executable file mode required")
        if binding(source)["sha256"] != row["sha256"]:
            raise ValueError(f"Pinned source changed: {source}")
    paths = [PurePosixPath(row["target"]) for row in files]
    if any(a in b.parents for a in paths for b in paths if a != b):
        raise ValueError("File/directory target collision")
    for key in ("python", "entrypoint"):
        if not isinstance(document.get(key), str) or not document[key]:
            raise ValueError("Explicit Python and inference/queue entrypoint required")
    python = Path(document["python"])
    if not python.is_absolute() or not python.is_file() or not os.access(python, os.X_OK):
        raise ValueError("Existing absolute executable Python required")
    if document["entrypoint"] not in seen:
        raise ValueError("Entrypoint must be part of exact staged files")
    if document.get("python_sha256") != binding(python)["sha256"]:
        raise ValueError("Pinned Python interpreter changed")
    return files


def stage(manifest, destination):
    manifest, destination = Path(manifest).resolve(), Path(destination)
    raw = manifest.read_bytes()
    document = json.loads(raw)
    files = validate(document, destination)
    destination.mkdir(parents=True, exist_ok=False)
    write_once(destination / "input-manifest.json", document)
    try:
        copied = []
        for row in files:
            data = Path(row["source"]).read_bytes()
            if digest(data) != row["sha256"]:
                raise ValueError("Source changed after validation")
            target = destination / row["target"]
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            target.chmod(row["mode"])
            copied.append(
                dict(
                    target=row["target"],
                    source=row["source"],
                    sha256=digest(data),
                    mode=row["mode"],
                )
            )
        if manifest.read_bytes() != raw:
            raise ValueError("Release manifest changed during staging")
        if binding(document["python"])["sha256"] != document["python_sha256"]:
            raise ValueError("Interpreter changed during staging")
        receipt = dict(
            schema=SCHEMA,
            state="staged-not-activated",
            model_id=document["model_id"],
            manifest=binding(manifest),
            python=binding(document["python"]),
            entrypoint=document["entrypoint"],
            files=copied,
            service_changes=0,
            acquisition_changes=0,
            legacy_output_changes=0,
        )
        write_once(destination / "stage.json", receipt)
        for name in ("input-manifest.json", "stage.json"):
            (destination / name).chmod(0o444)
        for folder in sorted(
            (p for p in destination.rglob("*") if p.is_dir()),
            key=lambda p: len(p.parts),
            reverse=True,
        ):
            folder.chmod(0o555)
        destination.chmod(0o555)
        return verify(destination)
    except BaseException as error:
        write_once(
            destination / "failure.json",
            dict(
                state="failed-stage-preserved",
                error_type=type(error).__name__,
                reason=str(error),
                service_changes=0,
            ),
        )
        raise


def verify(destination):
    destination = Path(destination)
    receipt = json.loads((destination / "stage.json").read_bytes())
    expected = {row["target"] for row in receipt["files"]} | {"input-manifest.json", "stage.json"}
    actual = {str(p.relative_to(destination)) for p in destination.rglob("*") if p.is_file()}
    if actual != expected or any(p.is_symlink() for p in destination.rglob("*")):
        raise ValueError("Exact release inventory changed")
    for row in receipt["files"]:
        path = destination / row["target"]
        if (
            binding(path)["sha256"] != row["sha256"]
            or stat.S_IMODE(path.stat().st_mode) != row["mode"]
        ):
            raise ValueError("Staged bytes or permissions changed")
    if binding(receipt["python"]["path"]) != receipt["python"]:
        raise ValueError("Staged interpreter binding changed")
    return receipt


def service_receipt(output):
    """Capture effective read-only service settings and every active drop-in byte."""
    output = Path(output)
    if output.exists():
        raise ValueError("New service receipt required")
    rows = {}
    for service in SERVICES:
        command = [
            "systemctl",
            "show",
            service,
            "--no-pager",
            "--property=FragmentPath,DropInPaths,ExecStart,User,Group,WorkingDirectory,ActiveState,SubState,MainPID,KillMode,TimeoutStopUSec",
        ]
        result = subprocess.run(command, check=True, capture_output=True, text=True, timeout=10)
        values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
        paths = [values["FragmentPath"], *shlex.split(values["DropInPaths"])]
        rows[service] = dict(
            properties=values,
            files=[dict(binding(path), text=Path(path).read_text()) for path in paths if path],
        )
    receipt = dict(
        schema="fast-shared-predeployment-services-v1",
        services=rows,
        captured_environment_file_contents=False,
        service_changes=0,
        rollback=(
            "Restore saved changed drop-ins; remove only newly added shared drop-ins. "
            "Daemon-reload, drain and restart affected analysis/API; retain all outputs."
        ),
        gates=[
            "Explicit source closure and dependency/ABI qualification",
            "Existing-corpus replay in isolated output namespace as service user",
            "Checkpoint/restart, immutable publication and unavailable-state tests",
            "Drain analyzer only; acquisition continues",
            "Verify new read-only model status API and manifest/artifact digests",
            "Separate idempotent shared backfill, preserving legacy completion/failure",
        ],
    )
    write_once(output, receipt)
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("stage", "verify", "service-receipt"))
    parser.add_argument("destination", type=Path)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    result = (
        stage(args.manifest, args.destination)
        if args.action == "stage"
        else verify(args.destination)
        if args.action == "verify"
        else service_receipt(args.destination)
    )
    print(json.dumps(dict(action=args.action, state=result.get("state", "captured-read-only"))))
